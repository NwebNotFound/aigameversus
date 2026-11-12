"""`config/models.yaml`: the spending limits and the models that can take a seat."""

import os
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "models.yaml"


class ConfigError(ValueError):
    """The file is broken; the message says which field."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# The environment variable that holds the API key of each provider.
KEY_VARIABLES = {"openrouter": "OPENROUTER_API_KEY"}


class Limits(_Strict):
    match_eur: Decimal = Field(gt=0)
    month_eur: Decimal = Field(gt=0)
    usd_to_eur: Decimal = Field(gt=0)
    max_input_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    # With adaptive_output: the most a cut-off answer is raised to (D-143).
    output_ceiling: int = Field(8000, gt=0)
    # How much a reasoning model may think before it answers; None leaves it to the model.
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None


Effort = Literal["minimal", "low", "medium", "high"]


class Model(_Strict):
    provider: Literal["openrouter"]
    model: str = Field(min_length=1)  # the provider's name for it
    name: str | None = Field(None, min_length=1)  # what people read; default: the id
    input_usd_per_mtok: Decimal = Field(ge=0)
    output_usd_per_mtok: Decimal = Field(ge=0)
    # What this model needs to play, over `limits`; unset: the value in `limits`.
    max_output_tokens: int | None = Field(None, gt=0)
    output_ceiling: int | None = Field(None, gt=0)  # this model's own, else limits'
    reasoning_effort: Effort | Literal["off"] | None = None  # "off": the option is not sent
    tool_choice: Literal["required", "auto"] = "required"  # auto: the model may also not call


@dataclass(frozen=True)
class CallOptions:
    """What every call of one model is sent with."""

    max_output_tokens: int
    reasoning_effort: Effort | None  # None: not sent
    tool_choice: Literal["required", "auto"]
    output_ceiling: int  # with adaptive_output, the most a cut-off answer is raised to


class ReliabilityRules(_Strict):
    """When a model counts as unreliable here (arena/db/reliability.py)."""

    moves: int = Field(20, gt=0)  # the newest moves a verdict rests on
    matches: int = Field(2, gt=0)  # a seat that gave up in one of these newest matches
    fallback_above: Decimal = Field(Decimal("0.5"), ge=0, le=1)  # share of bot moves
    cut_off_above: Decimal = Field(Decimal("0.1"), ge=0, le=1)  # share of cut-off moves
    throttled_above: Decimal = Field(Decimal("0.2"), ge=0)  # rate-limited calls per move
    # the warning that cut-offs explain the refusals: more than this share of the refused
    # answers ran into the output limit, with at least `cut_off_dominates_min` of them
    cut_off_dominates_above: Decimal = Field(Decimal("0.5"), ge=0, le=1)
    cut_off_dominates_min: int = Field(3, gt=0)


class Config(_Strict):
    limits: Limits
    models: dict[str, Model]
    reliability: ReliabilityRules = ReliabilityRules()


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Read and validate the file; raise ConfigError with a readable message."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigError(f"{path.name}: cannot read file: {error}") from error
    try:
        return Config.model_validate(data)
    except ValidationError as invalid:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in problem['loc']) or 'file'}: {problem['msg']}"
            for problem in invalid.errors()
        )
        raise ConfigError(f"{path.name}: {problems}") from invalid


def load_keys(config: Config, model_ids: Iterable[str]) -> list[str]:
    """Put the keys these models need into the environment; return the variables still missing.

    A key comes from its variable (`OPENROUTER_API_KEY`) or from the file that
    `<variable>_FILE` names, which wins and is read on every call, so a
    replaced file counts from the next match. LiteLLM reads the variable.
    Without its key every seat would fail at its first call, after that call
    was booked, and random bots would play on under the models' names.
    """
    needed = {KEY_VARIABLES[config.models[model_id].provider] for model_id in model_ids}
    for name in needed:
        _read_key_file(name)
    return sorted(name for name in needed if not os.environ.get(name))


def _read_key_file(variable: str) -> None:
    path = os.environ.get(f"{variable}_FILE")
    if not path:
        return
    try:
        key = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        key = ""
    if key:
        os.environ[variable] = key
    else:  # a key file that is gone or empty means no key, not the one read before
        os.environ.pop(variable, None)


def call_options(config: Config, model_id: str) -> CallOptions:
    """The options of `model_id`: its own where it sets them, else those of `limits`."""
    model, limits = config.models[model_id], config.limits
    start = model.max_output_tokens or limits.max_output_tokens
    effort = limits.reasoning_effort if model.reasoning_effort is None else model.reasoning_effort
    return CallOptions(
        max_output_tokens=start,
        reasoning_effort=None if effort == "off" else effort,
        tool_choice=model.tool_choice,
        # Never below the start: a model whose own limit is higher just starts there.
        output_ceiling=max(start, model.output_ceiling or limits.output_ceiling),
    )


def display_name(config: Config, model_id: str) -> str:
    return config.models[model_id].name or model_id
