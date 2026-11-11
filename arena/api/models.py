"""The page of one model: its rating, cost and tool errors per game."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from arena.api.ratings import RecentMatch, StandingOut, vendor_of
from arena.catalog import load
from arena.config import load_config
from arena.ratings.elo import PROVISIONAL_GAMES
from arena.ratings.store import RatingStore, Usage

router = APIRouter(tags=["models"])


def get_store(request: Request) -> RatingStore:
    return RatingStore(request.app.state.pool)


Store = Annotated[RatingStore, Depends(get_store)]


class ModelInfo(BaseModel):
    id: str
    vendor: str | None
    provider_model: str = Field(description="The provider's name for the model")
    input_usd_per_mtok: float
    output_usd_per_mtok: float


class UsageOut(BaseModel):
    cost_total_micro_eur: int | None = Field(description="null while the ledger cannot be read")
    cost_per_game_micro_eur: int | None = Field(
        description="null without a booked call, or while the ledger cannot be read"
    )
    answers: int = Field(description="Answers the server took or refused")
    tool_error_rate: float | None = Field(description="Refused answers over all answers")

    @classmethod
    def of(cls, used: Usage, games: int) -> "UsageOut":
        answers = used.accepted + used.rejected
        return cls(
            cost_total_micro_eur=used.cost_micro_eur,
            cost_per_game_micro_eur=(
                round(used.cost_micro_eur / games) if games and used.cost_micro_eur else None
            ),
            answers=answers,
            tool_error_rate=used.rejected / answers if answers else None,
        )


class GameOut(StandingOut):
    game_id: str
    usage: UsageOut


class Personality(BaseModel):
    profile_id: UUID
    personality_id: str


class ModelPage(BaseModel):
    model: ModelInfo | None = Field(description="null for a model that is not in the config")
    profile_id: UUID | None = Field(
        description="The profile without a personality; null until played"
    )
    overall: StandingOut | None
    provisional_games: int = Field(
        PROVISIONAL_GAMES, description="Rated games a rating needs before it counts as reliable"
    )
    usage: UsageOut
    games: list[GameOut]
    recent_matches: list[RecentMatch]
    personalities: list[Personality] = Field(
        description="Profiles of this model with a personality"
    )


class CatalogModel(BaseModel):
    id: str = Field(description="The id for POST /matches: config/models.yaml's if verified")
    openrouter_id: str
    name: str
    vendor: str
    context_length: int | None
    input_usd_per_mtok: float
    output_usd_per_mtok: float
    reasoning: bool = Field(description="Whether the model can think before it answers")
    moderated: bool
    free: bool
    verified: bool = Field(description="In config/models.yaml: prices and behaviour checked")
    price_source: str = Field(
        description='"config/models.yaml" (checked by hand) or "openrouter list" (not checked; '
        "booked at the listed price x 1.25)"
    )
    high_price: bool = Field(description="Output costs more than 10 USD per million tokens")


class CatalogOut(BaseModel):
    models: list[CatalogModel]
    fetched_at: datetime | None = Field(
        description="When OpenRouter's list was read; null: only config/models.yaml is known"
    )
    fresh: bool = Field(description="Read within the last hour; false: an older copy or none")


@router.get("/models/catalog")
async def model_catalog() -> CatalogOut:
    """Every model that can take a seat: config/models.yaml's, then OpenRouter's others.

    A model can play when it writes text and takes a forced tool call. The caps and
    confirm_spend hold for every model; unverified ones are priced at OpenRouter's prices.
    """
    catalog = await load(load_config())
    return CatalogOut(
        models=[
            CatalogModel(
                id=e.id,
                openrouter_id=e.openrouter_id,
                name=e.name,
                vendor=e.vendor,
                context_length=e.context_length,
                input_usd_per_mtok=float(e.input_usd_per_mtok),
                output_usd_per_mtok=float(e.output_usd_per_mtok),
                reasoning=e.reasoning,
                moderated=e.moderated,
                free=e.free,
                verified=e.verified,
                price_source=e.price_source,
                high_price=e.high_price,
            )
            for e in catalog.entries
        ],
        fetched_at=None
        if catalog.fetched_at is None
        else datetime.fromtimestamp(catalog.fetched_at, UTC),
        fresh=catalog.fresh,
    )


@router.get("/models/{model_id}")
async def model_page(model_id: str, store: Store, request: Request) -> ModelPage:
    """One model across all its matches and seats: rating per game, cost and tool errors.

    The id is the model's id in `config/models.yaml`. The profile it describes is the one
    without a personality; others are listed. Known models that have not played give an
    empty page; an id that is neither configured nor played is 404.
    """
    configured = load_config().models.get(model_id)
    profile_id = store.model_profile_id(model_id)
    found = await store.profile(profile_id)
    personalities = await store.other_personalities(model_id)
    if configured is None and found is None and not personalities:
        raise HTTPException(404, f"No model {model_id}")
    games: list[GameOut] = []
    usage_total = Usage()
    if found is not None:
        ledger = request.app.state.live.ledger
        usage_total = (await store.usage(ledger, None, profile_id)).get(profile_id, Usage())
        for game_id, standing in found.per_game.items():
            used = (await store.usage(ledger, game_id, profile_id)).get(profile_id, Usage())
            games.append(
                GameOut(
                    game_id=game_id,
                    usage=UsageOut.of(used, standing.games_played),
                    **StandingOut.of(standing).model_dump(),
                )
            )
    return ModelPage(
        model=ModelInfo(
            id=model_id,
            vendor=vendor_of(model_id),
            provider_model=configured.model,
            input_usd_per_mtok=float(configured.input_usd_per_mtok),
            output_usd_per_mtok=float(configured.output_usd_per_mtok),
        )
        if configured
        else None,
        profile_id=profile_id if found is not None else None,
        overall=StandingOut.of(found.overall) if found and found.overall else None,
        usage=UsageOut.of(
            usage_total, found.overall.games_played if found and found.overall else 0
        ),
        games=games,
        recent_matches=[
            RecentMatch(
                match_id=m.match_id,
                game_id=m.game_id,
                rated_at=m.rated_at,
                played_at=m.played_at,
                rank=m.rank,
                players=m.players,
                rating_change=round(m.rating_change, 1),
            )
            for m in (found.recent_matches if found else [])
        ],
        personalities=[Personality(profile_id=p, personality_id=n) for p, n in personalities],
    )
