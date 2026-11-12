"""Game list, match start, match records and the event stream for spectators.

Everything here shows a match the way a spectator sees it: all events, also
thoughts and hidden cards. The API listens on localhost only.
"""

import asyncio
import os
import time
from datetime import UTC, datetime
from functools import partial
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.websockets import WebSocketDisconnect

from arena.agents.budget import MICRO
from arena.agents.estimate import Basis, estimate
from arena.api.live import ArenaBusy, LiveMatches, NotRunning
from arena.catalog import HIGH_OUTPUT_USD_PER_MTOK, resolve
from arena.config import Config, load_config, load_keys
from arena.db.ledger import LedgerUnavailable
from arena.db.match_store import Batch, MatchRecord, Origin, Seat, Status
from arena.engine.replay import replay
from arena.engine.types import MATCH_BUDGET, Event, match_budget_of
from arena.personalities import load_personalities

router = APIRouter(tags=["matches"])

UNKNOWN_MATCH = 4404  # WebSocket close code, after HTTP 404


def get_live(request: Request) -> LiveMatches:
    return request.app.state.live


Live = Annotated[LiveMatches, Depends(get_live)]


class Game(BaseModel):
    id: str
    name: str
    min_players: int
    max_players: int


class SeatSpec(BaseModel):
    """Who takes one seat: a model (paid) or a random bot (free)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["model", "bot"]
    model: str | None = Field(None, description="For a model seat: an id of GET /models/catalog")
    personality: str | None = Field(
        None, description="For a model seat: a personality id of GET /setup, or none"
    )

    @model_validator(mode="after")
    def _check(self) -> "SeatSpec":
        if (self.kind == "model") != (self.model is not None):
            raise ValueError("a model seat names its model, a bot seat names none")
        if self.personality is not None and self.kind == "bot":
            raise ValueError("a random bot plays no personality")
        return self


class NewMatch(BaseModel):
    game: str = Field(description="Game id, see GET /games")
    players: int | None = Field(None, description="Number of seats; default: the game's minimum")
    models: list[str] | None = Field(
        None,
        min_length=1,
        description="Model ids from config/models.yaml, one per seat in order (p1, p2, ...). "
        "Makes paid model calls inside the cost caps. Only on a server started with "
        "ARENA_ALLOW_MODEL_SEATS=1, and with confirm_spend. Without: every seat is a random bot",
    )
    seats: list[SeatSpec] | None = Field(
        None,
        min_length=1,
        description="One entry per seat in order, a model or a bot: a table may mix them. "
        "Instead of `models`; any model seat needs what `models` needs.",
    )
    confirm_spend: bool = Field(
        False, description="Must be true for a match with model seats: it spends money."
    )
    seed: int | None = Field(None, ge=0, lt=2**63, description="Default: a random seed")
    settings: dict[str, Any] = Field(default_factory=dict, description="Settings of the game")
    turn_delay: float = Field(
        0, ge=0, le=60, description="Seconds to wait after each turn, so people can follow"
    )
    memory: bool = Field(
        True,
        description="False: a fair benchmark. The match neither reads nor writes any memory "
        "(relationships, match summaries).",
    )
    batch: Batch | None = Field(
        None, description="The batch this match belongs to, e.g. an experiment stage or a league"
    )


class EventOut(Event):
    seq: int = Field(description="Position in the log of the match, from 0")


@router.get("/games")
def list_games(live: Live) -> list[Game]:
    """Every game that can be played."""
    return [
        Game(id=g.id, name=g.name, min_players=g.min_players, max_players=g.max_players)
        for g in live.games.values()
    ]


ALLOW_MODEL_SEATS = "ARENA_ALLOW_MODEL_SEATS"


@router.post("/matches", status_code=201)
async def start_match(new: NewMatch, live: Live) -> MatchRecord:
    """Start a match of random bots, or of models (`models`). It plays on in the background.

    Model seats cost money and are refused (403) unless the server was started
    with ARENA_ALLOW_MODEL_SEATS=1: the API has no login. A model is an id of
    config/models.yaml or any other id of GET /models/catalog. Answers 429 while the
    server already plays as many matches as it does at a time.
    """
    plugin = live.games.get(new.game)
    if plugin is None:
        raise HTTPException(404, f"Unknown game {new.game!r}. Games: {', '.join(live.games)}")
    if MATCH_BUDGET in new.settings:
        _check_match_budget(new.settings[MATCH_BUDGET])
    if new.models is not None and new.seats is not None:
        raise HTTPException(422, "Name the seats with `seats` or with `models`, not both.")
    models = None
    personalities: dict[str, str] = {}
    if new.seats is not None:
        count = len(new.seats)
        if new.players is not None and new.players != count:
            raise HTTPException(422, f"players is {new.players}, but {count} seats are named")
        chosen = {f"p{i}": s.model for i, s in enumerate(new.seats, start=1) if s.kind == "model"}
        personalities = {
            f"p{i}": s.personality for i, s in enumerate(new.seats, start=1) if s.personality
        }
        known = {p.id for p in load_personalities()}
        if unknown := sorted(set(personalities.values()) - known):
            raise HTTPException(
                422,
                f"Unknown personality {', '.join(unknown)}. "
                f"Personalities: {', '.join(sorted(known))}",
            )
        if chosen:
            models = await _model_seats(new, chosen)
    elif new.models is None:
        count = new.players or plugin.min_players
    else:
        if new.players is not None and new.players != len(new.models):
            raise HTTPException(
                422,
                f"players is {new.players}, but {len(new.models)} models are named: one per seat",
            )
        models = await _model_seats(
            new, {f"p{seat}": model_id for seat, model_id in enumerate(new.models, start=1)}
        )
        count = len(models)
    players = [f"p{seat}" for seat in range(1, count + 1)]
    try:
        return await live.start(
            plugin,
            players,
            seed=new.seed,
            settings=new.settings,
            turn_delay=new.turn_delay,
            models=models,
            memory=new.memory,
            batch=new.batch,
            personalities=personalities,
        )
    except ValueError as refused:
        raise HTTPException(422, str(refused)) from refused
    except ArenaBusy as busy:
        raise HTTPException(429, str(busy)) from busy


def _check_match_budget(value: Any) -> None:
    """A match's own spend limit: euros above 0, at most the config's per-match cap (422)."""
    cap = load_config().limits.match_eur
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0 < value <= cap:
        raise HTTPException(
            422,
            f"{MATCH_BUDGET} is what this match may spend at most: a number of euros above 0 "
            f"and at most the per-match cap of {cap}, not {value!r}.",
        )


async def _model_seats(new: NewMatch, models: dict[str, str]) -> dict[str, str]:
    """Seat -> model id of the model seats, after every check that can refuse a paid match."""
    if os.environ.get(ALLOW_MODEL_SEATS) != "1":
        raise HTTPException(
            403,
            f"Model seats make paid calls and are off on this server. Start it with "
            f"{ALLOW_MODEL_SEATS}=1 to allow them.",
        )
    if not new.confirm_spend:
        raise HTTPException(
            422, "A match with model seats spends money: send confirm_spend: true to start it."
        )
    ids = list(models.values())
    config = await _seat_config(ids)
    if missing := load_keys(config, ids):
        raise HTTPException(
            503,
            f"The server lacks {', '.join(missing)}, the provider's API key. Nothing was started.",
        )
    return models


async def _seat_config(model_ids: list[str]) -> Config:
    """The config with these models in it: config/models.yaml's, or the catalog's.

    An unverified catalog model comes at its listed price x1.25, as the budget books it.
    Refuses (422) an id that is in neither.
    """
    config = await resolve(load_config(), model_ids)
    unknown = [model_id for model_id in model_ids if model_id not in config.models]
    if unknown:
        raise HTTPException(
            422,
            f"Unknown model {', '.join(unknown)}. Take an id of GET /models/catalog; "
            f"config/models.yaml has: {', '.join(load_config().models)}",
        )
    return config


class EstimateRequest(BaseModel):
    game: str = Field(description="Game id, see GET /games")
    models: list[str | None] = Field(
        min_length=1,
        description="Model ids of GET /models/catalog, one per seat in order; null for a bot "
        "seat, which plays but costs nothing",
    )
    settings: dict[str, Any] = Field(default_factory=dict, description="Settings of the game")


class SeatEstimateOut(BaseModel):
    model_id: str
    calls: int = Field(description="Prompts the seat got in the most expensive trial match")
    estimate_micro_eur: int
    basis: Basis = Field(
        description="Answers counted at the model's mean output in the ledger, or at the "
        "output limit while the ledger knows fewer than 10 of its answers (then several "
        "times too high)"
    )


class EstimateOut(BaseModel):
    estimate_micro_eur: int = Field(description="All seats together, in millionths of a euro")
    cap_micro_eur: int = Field(
        description="The cap of this match: the config's, or its own lower match_budget_eur"
    )
    month_spent_micro_eur: int = Field(description="What this calendar month has cost so far")
    month_cap_micro_eur: int
    seats: dict[str, SeatEstimateOut]
    fits: bool = Field(description="Whether the estimate fits the match cap and the month left")
    high_price: list[str] = Field(
        description="Models whose output costs more than 10 USD per million tokens, as booked"
    )


class Estimates:
    """One estimate at a time, and an answer kept for ESTIMATE_TTL seconds.

    The trial matches take the server's CPU, and the API has no login: without this,
    a client that asks again and again would slow every live match down.
    """

    def __init__(self):
        self.lock = asyncio.Lock()
        self.answers: dict[str, tuple[float, EstimateOut]] = {}


ESTIMATE_TTL = 30.0
_clock = time.monotonic  # seconds; a test moves it on


@router.post("/matches/estimate")
async def estimate_match(new: EstimateRequest, request: Request, live: Live) -> EstimateOut:
    """What a match of these models would cost, estimated without calling any model.

    Random bots play the match three times and every prompt a seat's model would get is
    measured; answers are counted at the model's mean output in the ledger, or at the output
    limit for a model with little history. A guide, not a promise: the caps still stop a
    match that costs more. Spends nothing and needs no flag. 503 while the ledger is down.
    One estimate runs at a time; the same request within 30 seconds gets the same answer.
    """
    estimates: Estimates = request.app.state.estimates
    key = new.model_dump_json()
    async with estimates.lock:
        kept = estimates.answers.get(key)
        if kept is not None and _clock() - kept[0] < ESTIMATE_TTL:
            return kept[1]
        answer = await _estimate(new, live)
        estimates.answers = {
            k: v for k, v in estimates.answers.items() if _clock() - v[0] < ESTIMATE_TTL
        }
        estimates.answers[key] = (_clock(), answer)
        return answer


async def _estimate(new: EstimateRequest, live: LiveMatches) -> EstimateOut:
    plugin = live.games.get(new.game)
    if plugin is None:
        raise HTTPException(404, f"Unknown game {new.game!r}. Games: {', '.join(live.games)}")
    ids = [model_id for model_id in new.models if model_id is not None]
    if not ids:
        raise HTTPException(422, "Every seat is a bot: a match of bots costs nothing.")
    if MATCH_BUDGET in new.settings:
        _check_match_budget(new.settings[MATCH_BUDGET])
    config = await _seat_config(ids)
    seats = {f"p{seat}": model_id for seat, model_id in enumerate(new.models, start=1)}
    history = await live.ledger.output_tokens(sorted(set(ids)))
    spent = await live.ledger.month_spent(datetime.now(UTC))
    try:  # bot matches take a moment of CPU: off the server's event loop
        per_seat = await asyncio.to_thread(
            lambda: asyncio.run(estimate(plugin, seats, new.settings, config, history))
        )
    except ValueError as refused:
        raise HTTPException(422, str(refused)) from refused
    total = sum(seat.estimate_micro_eur for seat in per_seat.values())
    # The match's own limit, if it sets one, is its cap (the lower of the two), as Budget has it.
    limit = match_budget_of(new.settings)
    cap = int(
        min(limit, config.limits.match_eur) * MICRO if limit else config.limits.match_eur * MICRO
    )
    month_cap = int(config.limits.month_eur * MICRO)
    return EstimateOut(
        estimate_micro_eur=total,
        cap_micro_eur=cap,
        month_spent_micro_eur=spent,
        month_cap_micro_eur=month_cap,
        seats={
            seat: SeatEstimateOut(
                model_id=e.model_id,
                calls=e.calls,
                estimate_micro_eur=e.estimate_micro_eur,
                basis=e.basis,
            )
            for seat, e in per_seat.items()
        },
        fits=total <= cap and spent + total <= month_cap,
        high_price=sorted(
            {
                model_id
                for model_id in ids
                if config.models[model_id].output_usd_per_mtok > HIGH_OUTPUT_USD_PER_MTOK
            }
        ),
    )


@router.get("/matches")
async def list_matches(
    live: Live,
    status: Annotated[list[Status] | None, Query(description="Only these statuses")] = None,
    batch: Annotated[str | None, Query(description="Only the matches of this batch id")] = None,
) -> list[MatchRecord]:
    """The newest 100 matches, newest first; with `batch`, every match of that batch."""
    return await live.matches.recent(status, batch)


@router.get("/matches/{match_id}")
async def get_match(match_id: UUID, live: Live) -> MatchRecord:
    record = await live.matches.get(match_id)
    if record is None:
        raise HTTPException(404, "Unknown match")
    return record


@router.get("/matches/{match_id}/events")
async def get_events(match_id: UUID, live: Live) -> list[EventOut]:
    """The log of a match so far, completed turns only."""
    if await live.matches.get(match_id) is None:
        raise HTTPException(404, "Unknown match")
    events = await live.log(match_id)
    return [EventOut(seq=seq, **event.model_dump()) for seq, event in enumerate(events)]


@router.websocket("/matches/{match_id}/events")
async def stream_events(websocket: WebSocket, match_id: UUID) -> None:
    """Send the log of a match from its first event, one JSON object per event.

    For a running match the stream goes on turn by turn and the server closes
    it when the match stops. An unknown match is closed with code 4404.
    """
    live: LiveMatches = websocket.app.state.live
    await websocket.accept()
    if await live.matches.get(match_id) is None:
        await websocket.close(UNKNOWN_MATCH, "Unknown match")
        return
    try:
        async for seq, event in live.events(match_id):
            out = EventOut(seq=seq, **event.model_dump())
            await websocket.send_json(out.model_dump(mode="json"))
        await websocket.close()
    except WebSocketDisconnect:
        pass  # the spectator left; the match plays on


class ControlOut(BaseModel):
    paused: bool
    turn_delay: float = Field(description="Seconds the match waits after each turn")


class Speed(BaseModel):
    turn_delay: float = Field(ge=0, le=60, description="Seconds to wait after each turn")


class Board(BaseModel):
    game: str
    events: int = Field(description="How many events of the log the board shows")
    spec: dict[str, Any] | None = Field(
        description="The game's render_spec of that state (spectator view, hidden parts "
        "included); null if the game has none yet"
    )


class Replay(BaseModel):
    id: UUID
    game: str
    players: list[str]
    winners: list[str] = Field(description="The players with rank 1")
    started_at: datetime
    finished_at: datetime
    cost_micro_eur: int | None = Field(
        description="What its model calls cost; 0 for bots, null while the ledger cannot be read"
    )
    seats: dict[str, Seat] | None = Field(description="Who played each seat; null for old rows")
    origin: Origin
    prompt_version: str | None = Field(
        description="Which prompt the models read (the game's prompt_version); null for old rows"
    )
    real: bool = Field(description="Whether a model played any seat")


class Cost(BaseModel):
    total_micro_eur: int = Field(description="Millionths of a euro, all players together")
    players: dict[str, int] = Field(description="Millionths of a euro per player")


async def _record(live: LiveMatches, match_id: UUID) -> MatchRecord:
    record = await live.matches.get(match_id)
    if record is None:
        raise HTTPException(404, "Unknown match")
    return record


def _controlled(action, match_id: UUID) -> ControlOut:
    try:
        control = action(match_id)
    except NotRunning as stopped:
        raise HTTPException(409, str(stopped)) from stopped
    return ControlOut(paused=control.paused, turn_delay=control.turn_delay)


@router.get("/matches/{match_id}/control")
async def get_control(match_id: UUID, live: Live) -> ControlOut:
    """Whether a running match is paused, and its delay between turns. 409 if it is not running."""
    await _record(live, match_id)
    return _controlled(live.control, match_id)


@router.post("/matches/{match_id}/pause")
async def pause_match(match_id: UUID, live: Live) -> ControlOut:
    """Stop a running match after its current turn, until it is resumed."""
    await _record(live, match_id)
    return _controlled(live.pause, match_id)


@router.post("/matches/{match_id}/resume")
async def resume_match(match_id: UUID, live: Live) -> ControlOut:
    await _record(live, match_id)
    return _controlled(live.resume, match_id)


@router.put("/matches/{match_id}/speed")
async def set_speed(match_id: UUID, speed: Speed, live: Live) -> ControlOut:
    """Change the delay after each turn of a running match, from its next turn on."""
    await _record(live, match_id)
    return _controlled(lambda m: live.set_delay(m, speed.turn_delay), match_id)


@router.post("/matches/{match_id}/abort")
async def abort_match(match_id: UUID, live: Live) -> MatchRecord:
    """Stop a running match for good. Its log stays readable; its status becomes `aborted`."""
    await _record(live, match_id)
    try:
        await live.abort(match_id)
    except NotRunning as stopped:
        raise HTTPException(409, str(stopped)) from stopped
    return await _record(live, match_id)


@router.get("/matches/{match_id}/board")
async def get_board(
    match_id: UUID,
    live: Live,
    events: Annotated[
        int | None, Query(ge=0, description="Only the first this many events (for replays)")
    ] = None,
    nation: Annotated[
        str | None,
        Query(
            description="The board as this player sees it, for the spoiler-free view "
            "(games with `render_spec_for` only)"
        ),
    ] = None,
) -> Board:
    """What the game draws for spectators, after the completed turns so far.

    With `events`, after that many events of the log instead: a replay can show
    the board at any point of a match. With `nation`, only what that player sees.
    """
    record = await _record(live, match_id)
    plugin = live.games.get(record.game)
    if plugin is None:
        raise HTTPException(404, f"The game {record.game!r} is not installed")
    render = getattr(plugin, "render_spec", None)
    if nation is not None:
        render = getattr(plugin, "render_spec_for", None)
        if render is None:
            raise HTTPException(422, f"{record.game} has no board for one player")
        if nation not in record.players:
            raise HTTPException(422, f"{nation!r} is not a player of this match")
        render = partial(render, nation=nation)
    log = await live.log(match_id)
    events = log if events is None else log[:events]
    spec = render(replay(plugin, events)) if render and events else None
    return Board(game=record.game, events=len(events), spec=spec)


@router.get("/matches/{match_id}/cost")
async def get_cost(match_id: UUID, live: Live) -> Cost:
    """What the model calls of a match have cost so far (bots cost nothing)."""
    await _record(live, match_id)
    players = await live.ledger.match_costs(match_id)
    return Cost(total_micro_eur=sum(players.values()), players=players)


@router.get("/replays")
async def list_replays(live: Live) -> list[Replay]:
    """The newest 100 finished matches, newest first, with winners and cost.

    While the ledger cannot be read the list still answers, with every cost null.
    """
    records = await live.matches.finished()
    try:
        costs = await live.ledger.costs([record.id for record in records])
    except LedgerUnavailable:  # the list stays readable; the costs are unknown, not 0
        costs = {}
    return [
        Replay(
            id=record.id,
            game=record.game,
            players=record.players,
            winners=[p.player for p in record.placements or [] if p.rank == 1],
            started_at=record.started_at,
            finished_at=record.finished_at,
            cost_micro_eur=costs.get(record.id),
            seats=record.seats,
            origin=record.origin,
            prompt_version=record.prompt_version,
            real=record.real,
        )
        for record in records
    ]
