"""What the new-match form offers: the models, the personalities and the cost caps."""

import json
from pathlib import Path

import yaml
from fastapi import APIRouter
from jsonschema import ValidationError, validate
from pydantic import BaseModel, Field

from arena.config import CONFIG_PATH, load_config

PERSONALITIES_DIR = CONFIG_PATH.parent / "personalities"

router = APIRouter(tags=["setup"])


class ModelOption(BaseModel):
    id: str = Field(description="Key in config/models.yaml")
    model: str = Field(description="The provider's name for it")


class Personality(BaseModel):
    id: str
    name: str
    description: str


class Caps(BaseModel):
    match_eur: float = Field(description="Default cost limit of one match, in euros")
    month_eur: float = Field(description="Limit of all matches of a calendar month, in euros")


class SetupOptions(BaseModel):
    model_seats: bool = Field(
        description="Whether POST /matches can seat a model yet. Until it can, every seat "
        "is a random bot and the models are listed for what comes."
    )
    models: list[ModelOption]
    personalities: list[Personality]
    caps: Caps


def load_personalities(directory: Path = PERSONALITIES_DIR) -> list[Personality]:
    """Every personality file, checked against its schema, in file-name order."""
    schema = json.loads((directory / "personality.schema.json").read_text(encoding="utf-8"))
    personalities = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            validate(data, schema)
        except ValidationError as error:
            raise ValueError(f"{path.name}: {error.message}") from None
        if data["id"] != path.stem:
            raise ValueError(f"{path.name}: id {data['id']!r} must match the file name")
        personalities.append(
            Personality(id=data["id"], name=data["name"], description=data["description"].strip())
        )
    return personalities


@router.get("/setup")
def setup_options() -> SetupOptions:
    """Models, personalities and cost caps for the new-match form."""
    config = load_config()
    return SetupOptions(
        model_seats=False,
        models=[ModelOption(id=key, model=model.model) for key, model in config.models.items()],
        personalities=load_personalities(),
        caps=Caps(
            match_eur=float(config.limits.match_eur), month_eur=float(config.limits.month_eur)
        ),
    )
