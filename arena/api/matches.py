"""Game list, match start, match records and the event stream for spectators.

Everything here shows a match the way a spectator sees it: all events, also
thoughts and hidden cards. The API listens on localhost only.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from arena.api.live import ArenaBusy, LiveMatches
from arena.db.match_store import MatchRecord, Status
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
