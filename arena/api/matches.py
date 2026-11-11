"""Game list, match start, match records and the event stream for spectators.

Everything here shows a match the way a spectator sees it: all events, also
thoughts and hidden cards. The API listens on localhost only.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from arena.api.live import ArenaBusy, LiveMatches, NotRunning
from arena.db.match_store import MatchRecord, Status
from arena.engine.replay import replay
from arena.engine.types import Event

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


class NewMatch(BaseModel):
    game: str = Field(description="Game id, see GET /games")
    players: int | None = Field(None, description="Number of seats; default: the game's minimum")
    seed: int | None = Field(None, ge=0, lt=2**63, description="Default: a random seed")
    settings: dict[str, Any] = Field(default_factory=dict, description="Settings of the game")
    turn_delay: float = Field(
        0, ge=0, le=60, description="Seconds to wait after each turn, so people can follow"
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


@router.post("/matches", status_code=201)
async def start_match(new: NewMatch, live: Live) -> MatchRecord:
    """Start a match in which every seat is a random bot. It plays on in the background.

    Answers 429 while the server already plays as many matches as it does at a time.
    """
    plugin = live.games.get(new.game)
    if plugin is None:
        raise HTTPException(404, f"Unknown game {new.game!r}. Games: {', '.join(live.games)}")
    players = [f"p{seat}" for seat in range(1, (new.players or plugin.min_players) + 1)]
    try:
        return await live.start(
            plugin, players, seed=new.seed, settings=new.settings, turn_delay=new.turn_delay
        )
    except ValueError as refused:
        raise HTTPException(422, str(refused)) from refused
    except ArenaBusy as busy:
        raise HTTPException(429, str(busy)) from busy


@router.get("/matches")
async def list_matches(
    live: Live,
    status: Annotated[list[Status] | None, Query(description="Only these statuses")] = None,
) -> list[MatchRecord]:
    """The newest 100 matches, newest first."""
    return await live.matches.recent(status)


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
async def get_board(match_id: UUID, live: Live) -> Board:
    """What the game draws for spectators, after the completed turns so far."""
    record = await _record(live, match_id)
    plugin = live.games.get(record.game)
    if plugin is None:
        raise HTTPException(404, f"The game {record.game!r} is not installed")
    events = await live.log(match_id)
    render = getattr(plugin, "render_spec", None)
    spec = render(replay(plugin, events)) if render and events else None
    return Board(game=record.game, events=len(events), spec=spec)


@router.get("/matches/{match_id}/cost")
async def get_cost(match_id: UUID, live: Live) -> Cost:
    """What the model calls of a match have cost so far (bots cost nothing)."""
    await _record(live, match_id)
    players = await live.ledger.match_costs(match_id)
    return Cost(total_micro_eur=sum(players.values()), players=players)
