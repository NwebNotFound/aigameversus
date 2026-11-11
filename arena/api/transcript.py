"""The readable transcript of a match: GET /matches/{id}/transcript.

One source of readable text for the live view, replays, exports and the command line
(`arena.transcript`). A match that is still running answers too; the lines grow with it.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from arena.api.live import LiveMatches
from arena.ratings.store import BOT_MODEL_ID
from arena.transcript import RENDERERS, TranscriptLine, render_match, to_markdown, to_text

router = APIRouter(tags=["transcript"])


class Player(BaseModel):
    """Who sits in a seat, for avatars and chips; null for a random bot or an unrated match."""

    name: str | None = None
    model: str | None = None


class Transcript(BaseModel):
    game: str
    lang: str
    spoilers: bool
    players: dict[
        str, Player
    ]  # seat to who sits there, in seat order; the same with or without spoilers
    lines: list[TranscriptLine]


@router.get("/matches/{match_id}/transcript", response_model=None)
async def transcript(
    request: Request,
    match_id: UUID,
    lang: Annotated[Literal["en", "de"], Query(description="Language of the lines")] = "en",
    spoilers: Annotated[
        bool, Query(description="Include hidden cards, roles, thoughts and whispers")
    ] = False,
    format: Annotated[
        Literal["json", "text", "markdown"], Query(description="Lines as JSON, text or Markdown")
    ] = "json",
    min_importance: Annotated[
        int, Query(ge=1, le=3, description="1 shows everything, 3 only the highlights")
    ] = 1,
) -> Transcript | PlainTextResponse:
    """The match as a play-by-play, one line per event, in the order they happened.

    Players are named "Name (model)" where the match was rated, else by seat id. Without
    `spoilers`, only what every player could see is told.
    """
    live: LiveMatches = request.app.state.live
    record = await live.matches.get(match_id)
    if record is None:
        raise HTTPException(404, f"No match {match_id}")
    if record.game not in RENDERERS:
        raise HTTPException(404, f"No transcript for {record.game} (known: {', '.join(RENDERERS)})")
    names = {**{p: p for p in record.players}, **await live.matches.seat_names(match_id)}
    lines = render_match(await live.log(match_id), names, lang, spoilers, game=record.game)
    lines = [line for line in lines if line.importance >= min_importance]
    if format == "json":
        profiles = await live.matches.seat_profiles(match_id)
        players = {
            seat: Player(name=profiles[seat][0], model=profiles[seat][1])
            if seat in profiles and profiles[seat][1] != BOT_MODEL_ID
            else Player()
            for seat in record.players
        }
        return Transcript(
            game=record.game, lang=lang, spoilers=spoilers, players=players, lines=lines
        )
    if format == "markdown":
        return PlainTextResponse(to_markdown(lines), media_type="text/markdown; charset=utf-8")
    return PlainTextResponse(to_text(lines), media_type="text/plain; charset=utf-8")
