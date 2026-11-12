"""The settings of Jev (config/jev.yaml), checked when loaded."""

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from arena.config import CONFIG_PATH

JEV_CONFIG = CONFIG_PATH.parent / "jev.yaml"


class Threshold(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_options: int = Field(ge=2)
    min_top_probability: float = Field(gt=0, le=1)


class JevConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str
    endpoint: str
    timeout_seconds: float = Field(gt=0)
    input_usd_per_mtok: Decimal = Field(gt=0)
    reasoning_chars: int = Field(ge=0)
    situation_chars: int = Field(ge=0)
    max_options: int = Field(ge=2)
    samples: int = Field(ge=1)
    thresholds: list[Threshold] = Field(min_length=1)

    @model_validator(mode="after")
    def _covers(self) -> "JevConfig":
        bounds = [t.max_options for t in self.thresholds]
        if bounds != sorted(bounds) or len(set(bounds)) != len(bounds):
            raise ValueError("thresholds must be in rising order of max_options")
        if bounds[-1] < self.max_options:
            raise ValueError(f"no threshold covers {self.max_options} options")
        return self

    def threshold(self, options: int) -> float:
        """The top probability Jev's pick needs, for this many options."""
        return next(t.min_top_probability for t in self.thresholds if options <= t.max_options)


def load_jev_config(path: Path = JEV_CONFIG) -> JevConfig:
    return JevConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
