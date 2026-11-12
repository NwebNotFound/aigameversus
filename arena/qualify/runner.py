"""The qualification runner: one model, one game, one frozen configuration (research/QUALIFY.md).

Each core case sends one real turn request through the production path (`ModelAgent`, the
prompt builder, the metered call) and judges the FIRST model response only:

- clean: a valid action at once, nothing repaired, not cut off, the thought where required;
- repaired: the same, but the deployed v1 repair read the call (only with answer_repair v1);
- failed: no tool call, a garbled call, a cut-off answer, an illegal move, a missing
  required thought, the turn timeout, or a request the provider explicitly refused;
- unknown: a rate limit, an outage, a provider error, a budget stop, or no fixture.

The job is unqualified if any case failed, else unknown if any case is unknown, else
qualified (with the "repaired (v1)" badge if any case needed the repair). Corrections are
never asked: a later answer cannot rescue a failed first one.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from importlib import metadata
from typing import Any

import jsonschema

from arena.agents.budget import cost_micro_eur
from arena.agents.model import RATE_LIMITED, Message, ModelCall, ModelError, ModelReply
from arena.agents.runner import MAX_RETRIES, ModelAgent
from arena.config import Config, call_options
from arena.engine.match import DEFAULT_TURN_TIMEOUT
from arena.engine.plugin import GamePlugin
from arena.engine.types import (
    ANSWER_REPAIR,
    THOUGHT_HEADLINE,
    Action,
    AgentError,
    MatchPaused,
    ToolSpec,
)
from arena.qualify.fixtures import Fixture, capture
from arena.qualify.manifest import MANIFEST_VERSION, GameManifest

PROTOCOL = "research/QUALIFY.md v2"
SCOPE = "core"
FRESH_DAYS = 7
# The one explicit refusal of the frozen configuration: a parameter or the tools are not
# supported. A generic 400 (BadRequestError) is no such evidence: the request, the fixture
# or the context may be at fault, so it stays unknown with its reason, like every other
# provider failure (Researcher, #156).
REFUSED = {"UnsupportedParamsError"}
TOO_LONG = "PromptTooLong"


@dataclass
class CaseResult:
    case: str
    check: str
    outcome: str  # clean, repaired, failed, unknown
    reason: str | None = None
    seed: int | None = None
    fixture_sha256: str | None = None
    offered: list[str] = field(default_factory=list)
    tool: str | None = None
    validator: str | None = None  # the game's or the schema's refusal, if any
    thought: bool = False
    thought_profile: str = "optional"  # "required" or "optional", as the case declares
    warning: str | None = None
    cut_off: bool = False
    repairs: list[str] = field(default_factory=list)
    retries: int = 0
    rate_limits: int = 0
    latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    reasoning_tokens: int | None = None


@dataclass
class Verdict:
    status: str  # qualified, unqualified, unknown
    badge: str | None  # "repaired (v1)" on a qualified repair-enabled configuration
    reasons: list[str]
    cases: list[CaseResult]

    @property
    def counts(self) -> dict[str, int]:
        return {
            outcome: sum(1 for c in self.cases if c.outcome == outcome)
            for outcome in ("clean", "repaired", "failed", "unknown")
        }


def fixtures_of(plugin: GamePlugin, manifest: GameManifest) -> dict[str, Fixture | None]:
    """Every core case's fixture; None for a case no search match could give."""
    return {
        case.id: capture(
            plugin,
            manifest.players,
            manifest.settings,
            manifest.player,
            case.fits,
            case.offer,
            case=case.id,
            longest=case.longest,
        )
        for case in manifest.cases
    }


def settings_of(answer_repair: str, thought_headline: bool) -> dict[str, Any]:
    return {ANSWER_REPAIR: answer_repair, THOUGHT_HEADLINE: thought_headline}


async def requests_of(
    plugin: GamePlugin, fixtures: dict[str, Fixture | None], settings: dict[str, Any]
) -> dict[str, tuple[list[Message], list[dict[str, Any]]]]:
    """What the production path sends for each case: the messages and the tool schemas."""
    sent: dict[str, tuple[list[Message], list[dict[str, Any]]]] = {}
    for case, fixture in fixtures.items():
        if fixture is None:
            continue

        async def record(messages, tools, case=case):
            sent[case] = (messages, tools)
            return ModelReply()

        await ModelAgent(record, plugin, settings=settings).act(fixture.request)
    return sent


def bound_micro_eur(config: Config, model_id: str, sent) -> int:
    """The most the job can book: every case at its booking bound, with every transport retry."""
    model = config.models[model_id]
    out = call_options(config, model_id).max_output_tokens
    per_try = sum(
        cost_micro_eur(config, model, len(json.dumps([messages, tools])), out)
        for messages, tools in sent.values()
    )
    return per_try * (1 + MAX_RETRIES)


def configuration(
    plugin: GamePlugin,
    manifest: GameManifest,
    fixtures: dict[str, Fixture | None],
    sent,
    config: Config,
    model_id: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Everything a result depends on, canonical; no key, no account, no timestamp."""
    model = config.models[model_id]
    options = call_options(config, model_id)

    def digest(value: Any) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    return {
        "protocol": PROTOCOL,
        "manifest": MANIFEST_VERSION,
        "scope": SCOPE,
        "arena": {
            "version": metadata.version("aigameversus"),
            "commit": os.environ.get("ARENA_COMMIT", "unrecorded"),
        },
        "game": {
            "id": plugin.id,
            "version": plugin.version,
            "prompt_version": plugin.prompt_version(manifest.settings),
            "settings": manifest.settings,
        },
        "fixtures": {
            case: None if f is None else {"seed": f.seed, "sha256": f.sha256}
            for case, f in fixtures.items()
        },
        # Each case's check and whether its thought is required (the frozen profile).
        "cases": {
            case.id: {
                "check": case.check,
                "thought": "required" if case.thought_required else "optional",
            }
            for case in manifest.cases
        },
        # The prompt and tool schemas exactly as sent: rules, system text, history.
        "requests": {case: digest(request) for case, request in sorted(sent.items())},
        "model": {
            "id": model_id,
            "provider": model.provider,
            "provider_model": model.model,
            "route": "automatic route",  # the serving provider is not pinned
            "fallback": "none",
        },
        "call": {
            "max_input_tokens": config.limits.max_input_tokens,
            "max_output_tokens": options.max_output_tokens,
            "reasoning_effort": options.reasoning_effort,
            "tool_choice": options.tool_choice,
            "sampling": "provider_default",
            "timeout_seconds": DEFAULT_TURN_TIMEOUT,
            "transport_retries": MAX_RETRIES,
        },
        "runtime": {**settings, "memory": "off", "private_plan": "off"},
    }


def config_hash(configuration_: dict[str, Any]) -> str:
    canonical = json.dumps(configuration_, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def check(plugin: GamePlugin, state: Any, player: str, action: Action, tools: list[ToolSpec]):
    """The engine's own check of a move: an offered tool, its schema, then the game's rules."""
    spec = next((tool for tool in tools if tool.name == action.tool), None)
    if spec is None:
        return f"Tool '{action.tool}' was not offered"
    try:
        jsonschema.validate(action.arguments, spec.parameters)
    except jsonschema.ValidationError as invalid:
        return f"Invalid arguments for '{action.tool}': {invalid.message}"
    return plugin.validate(state, player, action)


async def run_case(
    plugin: GamePlugin,
    manifest: GameManifest,
    case_id: str,
    fixture: Fixture | None,
    call: ModelCall,
    settings: dict[str, Any],
    *,
    timeout: float = DEFAULT_TURN_TIMEOUT,
    clock: Callable[[], float] = time.monotonic,
) -> CaseResult:
    case = next(c for c in manifest.cases if c.id == case_id)
    result = CaseResult(case=case.id, check=case.check, outcome="unknown")
    if fixture is None:
        result.reason = "no fixture: no search match reached this situation"
        return result
    result.thought_profile = "required" if case.thought_required else "optional"
    result.seed, result.fixture_sha256 = fixture.seed, fixture.sha256
    result.offered = [tool.name for tool in fixture.request.tools]
    agent = ModelAgent(call, plugin, settings=settings, sleep=_no_wait, jitter=lambda: 0.0)
    started = clock()
    try:
        reply = await asyncio.wait_for(agent.act(fixture.request), timeout)
    except TimeoutError:
        return _failed(result, f"model turn timeout ({timeout:g} s)")
    except AgentError as error:
        return _provider(result, error)
    finally:
        result.latency_ms = round((clock() - started) * 1000)
    stats = reply.stats
    if stats is not None:
        result.cut_off, result.repairs = stats.cut_off, list(stats.repairs)
        result.retries, result.rate_limits = stats.retries, stats.rate_limits
        result.tokens_in, result.tokens_out = stats.tokens_in, stats.tokens_out
        result.reasoning_tokens = stats.reasoning_tokens
    result.thought = bool(reply.thought)
    if result.cut_off:
        return _failed(result, "cut off at the output limit")
    if reply.action is None:
        return _failed(result, f"malformed: {reply.problem}")
    result.tool = reply.action.tool
    refusal = check(
        plugin, fixture.state, manifest.player, reply.action, list(fixture.request.tools)
    )
    if refusal is not None:
        result.validator = refusal
        return _failed(result, f"invalid move: {refusal}")
    if not result.thought:
        if case.thought_required:
            return _failed(result, "missing required thought")
        result.warning = "no thought"
    result.outcome = "repaired" if result.repairs else "clean"
    return result


async def _no_wait(_: float) -> None:
    """Transport retries are not waited out in a qualification: a job is a few seconds."""


def _failed(result: CaseResult, reason: str) -> CaseResult:
    result.outcome, result.reason = "failed", reason
    return result


def _provider(result: CaseResult, error: AgentError) -> CaseResult:
    cause = error.__cause__
    kind = cause.reason if isinstance(cause, ModelError) else "provider error"
    if kind in REFUSED:
        return _failed(result, f"the provider refused the request ({kind})")
    result.reason = {
        RATE_LIMITED: "rate limited",
        TOO_LONG: "prompt longer than max_input_tokens",
        "BadRequestError": "the provider refused the request (BadRequestError): no evidence "
        "of unsupported tools or parameters",
    }.get(kind, f"provider unavailable ({kind})")
    return result


async def run_job(
    plugin: GamePlugin,
    manifest: GameManifest,
    fixtures: dict[str, Fixture | None],
    call_for: Callable[[str], ModelCall],
    settings: dict[str, Any],
    *,
    timeout: float = DEFAULT_TURN_TIMEOUT,
) -> Verdict:
    """Every case in order, serially, each with fresh state. A budget stop ends the job."""
    results: list[CaseResult] = []
    for case in manifest.cases:
        if results and results[-1].reason == "budget stop":
            results.append(CaseResult(case.id, case.check, "unknown", "not run: budget stop"))
            continue
        try:
            results.append(
                await run_case(
                    plugin,
                    manifest,
                    case.id,
                    fixtures.get(case.id),
                    call_for(case.id),
                    settings,
                    timeout=timeout,
                )
            )
        except MatchPaused:
            results.append(CaseResult(case.id, case.check, "unknown", "budget stop"))
    return verdict(results, settings.get(ANSWER_REPAIR, "off"))


def verdict(results: list[CaseResult], answer_repair: str) -> Verdict:
    """unqualified > unknown > qualified: a failure is evidence, an outage is not."""
    failed = [c for c in results if c.outcome == "failed"]
    unknown = [c for c in results if c.outcome == "unknown"]
    if failed:
        return Verdict("unqualified", None, [f"{c.case}: {c.reason}" for c in failed], results)
    if unknown:
        return Verdict("unknown", None, [f"{c.case}: {c.reason}" for c in unknown], results)
    repaired = any(c.outcome == "repaired" for c in results)
    assert not repaired or answer_repair == "v1", "only v1 repairs a first response"
    return Verdict("qualified", "repaired (v1)" if repaired else None, [], results)


def as_json(verdict_: Verdict) -> list[dict[str, Any]]:
    return [asdict(case) for case in verdict_.cases]
