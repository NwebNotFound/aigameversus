"""A typed client of Jev's decisions API (`POST /api/alpha/decisions`), and a fake for tests.

A call takes a `state` (any JSON) and `questions` keyed by our own ids; each question is
`noul` (yes/no), `choice` (one of named options) or `score` (ordered levels). The answer
carries a probability per option and `usage.cost` in US dollars.

`HttpJev` refuses to send anything unless the server runs with ARENA_ALLOW_JEV=1: no real
Jev call until that is decided. The key comes from OPENROUTER_API_KEY at call time and is
never logged. Every match wraps the client in `Budget.jev`, so each call is booked.
"""

import math
import os
from collections.abc import Mapping
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

ALLOW_JEV = "ARENA_ALLOW_JEV"
KEY_VARIABLE = "OPENROUTER_API_KEY"
SUM_TOLERANCE = 1e-6  # how far a choice's probabilities may sum from 1


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", allow_inf_nan=False)


class ChoiceAnswer(_Frozen):
    type: Literal["choice"]
    choice: str
    probabilities: dict[str, float]
    confidence: float | None = None

    @property
    def top_probability(self) -> float:
        return max(self.probabilities.values())


class NoulAnswer(_Frozen):
    type: Literal["noul"]
    probability: float = Field(ge=0, le=1)


class ScoreAnswer(_Frozen):
    type: Literal["score"]
    score: float
    probabilities: list[float]
    confidence: float | None = None
    legend: list[str] = []


Answer = ChoiceAnswer | NoulAnswer | ScoreAnswer


class Usage(_Frozen):
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = Field(0.0, ge=0, description="US dollars")


class JevResult(_Frozen):
    answers: dict[str, Answer]
    usage: Usage = Usage()


class JevError(Exception):
    """A Jev call that gave no usable answer. `reason` names the kind, never a message."""

    def __init__(self, reason: str):
        super().__init__(reason)
        # disabled, timeout, rate_limited, http, bad_answer; cost_over_bound (Budget.jev)
        self.reason = reason


class JevClient(Protocol):
    async def __call__(
        self, state: Any, questions: Mapping[str, Mapping[str, Any]]
    ) -> JevResult: ...


def parse(body: Any, questions: Mapping[str, Mapping[str, Any]]) -> JevResult:
    """Jev's answer, checked: every question answered, of the type asked. JevError if not."""
    try:
        result = JevResult.model_validate(body)
    except ValidationError:
        raise JevError("bad_answer") from None
    for key, question in questions.items():
        answer = result.answers.get(key)
        if answer is None or answer.type != question.get("type"):
            raise JevError("bad_answer")
        if isinstance(answer, ChoiceAnswer) and not _a_distribution(answer, question):
            raise JevError("bad_answer")
    return result


def _a_distribution(answer: ChoiceAnswer, question: Mapping[str, Any]) -> bool:
    """A probability for exactly the options asked, each in [0, 1], summing to 1, and the
    choice one of the most probable (research/JEV)."""
    options = set(question.get("criteria", {}))
    values = answer.probabilities
    if set(values) != options or answer.choice not in options:
        return False
    if not all(math.isfinite(p) and 0 <= p <= 1 for p in values.values()):
        return False
    if abs(math.fsum(values.values()) - 1) > SUM_TOLERANCE:
        return False
    return values[answer.choice] == max(values.values())


class HttpJev:
    """The real client. Sends nothing unless ARENA_ALLOW_JEV=1."""

    def __init__(
        self,
        model: str,
        endpoint: str,
        timeout_seconds: float,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        """`transport`: for tests only (httpx.MockTransport); the network otherwise."""
        self._model = model
        self._endpoint = endpoint
        self._timeout = timeout_seconds
        self._transport = transport

    async def __call__(self, state: Any, questions: Mapping[str, Mapping[str, Any]]) -> JevResult:
        if os.environ.get(ALLOW_JEV) != "1":
            raise JevError("disabled")
        key = os.environ.get(KEY_VARIABLE)
        if not key:
            raise JevError("disabled")
        request = {"model": self._model, "state": state, "questions": dict(questions)}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as http:
                response = await http.post(
                    self._endpoint, json=request, headers={"Authorization": f"Bearer {key}"}
                )
        except httpx.TimeoutException:
            raise JevError("timeout") from None
        except httpx.HTTPError:
            raise JevError("http") from None
        if response.status_code == 429:
            raise JevError("rate_limited")
        if response.status_code != 200:
            raise JevError("http")
        try:
            body = response.json()
        except ValueError:
            raise JevError("bad_answer") from None
        return parse(body, questions)


class FakeJev:
    """Answers from a script, for tests: a JevResult/dict per call, or a JevError to raise.

    `calls` holds every (state, questions) it was sent.
    """

    def __init__(self, *script: Any):
        self._script = list(script)
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    async def __call__(self, state: Any, questions: Mapping[str, Mapping[str, Any]]) -> JevResult:
        self.calls.append((state, dict(questions)))
        if not self._script:
            raise JevError("bad_answer")
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        if callable(step):
            step = step(state, questions)
        return step if isinstance(step, JevResult) else parse(step, questions)
