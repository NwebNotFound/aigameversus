"""Variant data for Liar's Deck: loading and validation only, no game logic."""

import json
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

VARIANTS_DIR = Path(__file__).parent / "variants"
SCHEMA_PATH = VARIANTS_DIR / "variant.schema.json"


class VariantError(ValueError):
    """A variant file is broken; the message says which file and which field."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlayerRange(_Strict):
    min: int = Field(ge=2)
    max: int = Field(ge=2)


class Deck(_Strict):
    kings: int = Field(ge=0)
    queens: int = Field(ge=0)
    aces: int = Field(ge=0)
    jokers: int = Field(ge=0)

    @property
    def total(self) -> int:
        return self.kings + self.queens + self.aces + self.jokers


class PlayRule(_Strict):
    min_cards: int = Field(ge=1)
    max_cards: int = Field(ge=1)


class Revolver(_Strict):
    chambers: int = Field(ge=1)
    live: int = Field(ge=1)


class DevilCard(_Strict):
    card: Literal["joker"]
    count: int = Field(ge=1)
    trigger: Literal["revealed_on_liar_call"]
    effect: Literal["all_others_shoot"]
    replaces_normal_shot: bool


class Variant(_Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    players: PlayerRange
    deck: Deck
    hand_size: int = Field(ge=1)
    play: PlayRule
    revolver: Revolver
    devil_card: DevilCard | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.players.min > self.players.max:
            raise ValueError("players.min must not exceed players.max")
        if self.play.min_cards > self.play.max_cards:
            raise ValueError("play.min_cards must not exceed play.max_cards")
        if self.play.max_cards > self.hand_size:
            raise ValueError("play.max_cards must not exceed hand_size")
        if self.revolver.live > self.revolver.chambers:
            raise ValueError("revolver.live must not exceed revolver.chambers")
        if self.hand_size * self.players.max > self.deck.total:
            raise ValueError(
                f"deck of {self.deck.total} cards is too small to deal "
                f"{self.hand_size} cards to {self.players.max} players"
            )
        if self.devil_card and self.devil_card.count > self.deck.jokers:
            raise ValueError("devil_card.count must not exceed deck.jokers")
        return self


def json_schema() -> dict:
    """The JSON Schema of a variant file, as stored in variant.schema.json."""
    return Variant.model_json_schema()


def load_variant(path: Path) -> Variant:
    """Read and validate one variant file; raise VariantError with a readable message."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise VariantError(f"{path.name}: cannot read file: {exc}") from exc
    try:
        variant = Variant.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'file'}: {e['msg']}" for e in exc.errors()
        )
        raise VariantError(f"{path.name}: {problems}") from exc
    if variant.id != path.stem:
        raise VariantError(f"{path.name}: id '{variant.id}' must match the file name")
    return variant


def load_variants(directory: Path = VARIANTS_DIR) -> dict[str, Variant]:
    """Load every variant in a directory, keyed by id."""
    return {v.id: v for v in (load_variant(p) for p in sorted(directory.glob("*.yaml")))}


if __name__ == "__main__":  # regenerate the schema file: python -m games.liars_deck.variants
    SCHEMA_PATH.write_text(json.dumps(json_schema(), indent=2) + "\n", encoding="utf-8")
