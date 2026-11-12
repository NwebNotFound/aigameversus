"""What the new-match form offers: models, personalities, cost caps and this month's spend."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import yaml
from fastapi import APIRouter, Request
from jsonschema import ValidationError, validate
from pydantic import BaseModel, Field

from arena.agents.budget import MICRO
from arena.api.matches import ALLOW_MODEL_SEATS
from arena.config import CONFIG_PATH, display_name, load_config, load_keys

PERSONALITIES_DIR = CONFIG_PATH.parent / "personalities"

router = APIRouter(tags=["setup"])


class ModelOption(BaseModel):
    id: str = Field(description="Key in config/models.yaml")
    model: str = Field(description="The provider's name for it")
    name: str = Field(description="What people read; the id when models.yaml gives no name")
    input_usd_per_mtok: float = Field(description="Price per million input tokens, US dollars")
    output_usd_per_mtok: float = Field(description="Price per million output tokens, US dollars")


class Personality(BaseModel):
    id: str
    name: str
    description: str


class Caps(BaseModel):
    match_eur: float = Field(description="Default cost limit of one match, in euros")
    month_eur: float = Field(description="Limit of all matches of a calendar month, in euros")


class SetupOptions(BaseModel):
    model_seats: bool = Field(
        description="Whether POST /matches seats models on this server: it was started with "
        "ARENA_ALLOW_MODEL_SEATS=1 and has the providers' API keys. Otherwise every seat is "
        "a random bot."
    )
    mixed_seats: bool = Field(
        True,
        description="Whether POST /matches takes `seats`, so models and random bots share a table",
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
    allowed = os.environ.get(ALLOW_MODEL_SEATS) == "1" and not load_keys(config, config.models)
    return SetupOptions(
        model_seats=allowed,
        models=[
            ModelOption(
                id=key,
                model=model.model,
                name=display_name(config, key),
                input_usd_per_mtok=float(model.input_usd_per_mtok),
                output_usd_per_mtok=float(model.output_usd_per_mtok),
            )
            for key, model in config.models.items()
        ],
        personalities=load_personalities(),
        caps=Caps(
            match_eur=float(config.limits.match_eur), month_eur=float(config.limits.month_eur)
        ),
    )


class MonthSpend(BaseModel):
    month: str = Field(description="The calendar month (UTC), YYYY-MM")
    spent_micro_eur: int = Field(description="Every model call of the month, millionths of a euro")
    cap_micro_eur: int
    remaining_micro_eur: int = Field(description="What the month cap still allows; 0 at the cap")


@router.get("/ledger/month")
async def month_spend(request: Request) -> MonthSpend:
    """What model calls have cost this month, and what the month cap still allows.

    503 when the spend ledger cannot be read: the month is then unknown, not 0.
    """
    now = datetime.now(UTC)
    # Through the arena's ledger, so a ledger of its own (another database) is read too.
    spent = await request.app.state.live.ledger.month_spent(now)
    cap = int(load_config().limits.month_eur * MICRO)
    return MonthSpend(
        month=now.strftime("%Y-%m"),
        spent_micro_eur=spent,
        cap_micro_eur=cap,
        remaining_micro_eur=max(0, cap - spent),
    )
