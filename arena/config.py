"""`config/models.yaml`: the spending limits and the models that can take a seat."""

from decimal import Decimal
import os
from collections.abc import Iterable
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
    # How much a reasoning model may think before it answers; None leaves it to the model.
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None


class Model(_Strict):
    provider: Literal["openrouter"]
    model: str = Field(min_length=1)  # the provider's name for it
    input_usd_per_mtok: Decimal = Field(ge=0)
    output_usd_per_mtok: Decimal = Field(ge=0)


class Config(_Strict):
    limits: Limits
    models: dict[str, Model]


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


def missing_keys(config: Config, model_ids: Iterable[str]) -> list[str]:
    """The key variables that the providers of these models need and the environment lacks.

    Without its key every seat would fail at its first call, after that call
    was booked, and random bots would play on under the models' names.
    """
    needed = {KEY_VARIABLES[config.models[model_id].provider] for model_id in model_ids}
    return sorted(name for name in needed if not os.environ.get(name))
