"""How facts turn into trust: the rules of `config/memory/trust.yaml` and one match's changes."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from arena.engine.types import PlayerId
from arena.memory.facts import KINDS, Fact

TRUST_PATH = Path(__file__).resolve().parents[2] / "config" / "memory" / "trust.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Limits(_Strict):
    min: int = Field(le=0)
    max: int = Field(ge=0)
    notes: int = Field(ge=0, description="Notes kept per pair, newest first")


class FactRule(_Strict):
    trust: int
    note: str = Field(min_length=1)


class TrustRules(_Strict):
    limits: Limits
    facts: dict[str, dict[str, FactRule]]

    @model_validator(mode="after")
    def _every_fact_has_a_rule(self) -> "TrustRules":
        for game, kinds in KINDS.items():
            missing = kinds - set(self.facts.get(game, {}))
            if missing:
                raise ValueError(f"{game}: no rule for {', '.join(sorted(missing))}")
        for game, rules in self.facts.items():
            unknown = set(rules) - KINDS.get(game, set())
            if unknown:
                raise ValueError(f"{game}: no fact is called {', '.join(sorted(unknown))}")
        return self

    def clamp(self, trust: int) -> int:
        return max(self.limits.min, min(self.limits.max, trust))


def load_rules(path: Path = TRUST_PATH) -> TrustRules:
    """The trust rules, checked; ValueError names the file and the problem."""
    try:
        return TrustRules.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (ValidationError, yaml.YAMLError) as error:
        raise ValueError(f"{path.name}: {error}") from None


@dataclass
class Change:
    """What one match does to one observer's view of one other player."""

    trust: int = 0
    notes: list[str] = field(default_factory=list)  # in the order the facts happened


def match_changes(
    game_id: str, facts: Iterable[Fact], rules: TrustRules
) -> dict[tuple[PlayerId, PlayerId], Change]:
    """Per (observer, about): the summed trust and the notes of a match's facts."""
    changes: dict[tuple[PlayerId, PlayerId], Change] = {}
    for fact in facts:
        rule = rules.facts[game_id][fact.kind]
        change = changes.setdefault((fact.observer, fact.about), Change())
        change.trust += rule.trust
        change.notes.append(rule.note.format(round=fact.round))
    return changes
