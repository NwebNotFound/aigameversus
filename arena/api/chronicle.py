"""The chronicle of a finished match: GET /matches/{id}/chronicle."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from arena.api.live import LiveMatches
from arena.chronicle import Chronicle, ChronicleError, chronicle_games, tell, to_markdown

router = APIRouter(tags=["chronicle"])


@router.get("/matches/{match_id}/chronicle", response_model=None)
async def chronicle(
    request: Request,
    match_id: UUID,
    style: Annotated[
        Literal["epic", "news", "sports", "novel"], Query(description="How the story is told")
    ] = "epic",
    lang: Annotated[Literal["en", "de"], Query(description="Language of the story")] = "en",
    format: Annotated[
        Literal["json", "markdown"], Query(description="Chapters as JSON, or one Markdown text")
    ] = "json",
) -> Chronicle | PlainTextResponse:
    """The story of a finished match, from its stored log. Spectator information: it names
    hidden cards and roles, so a match that is still running answers 409."""
    live: LiveMatches = request.app.state.live
    record = await live.matches.get(match_id)
    if record is None:
        raise HTTPException(404, f"No match {match_id}")
    if record.game not in chronicle_games():
        raise HTTPException(
            404, f"No chronicle for {record.game} (games with one: {', '.join(chronicle_games())})"
        )
    if record.status != "finished":
        raise HTTPException(
            409, f"The match is {record.status}; its chronicle exists once it has finished"
        )
    try:
        story = tell(await live.log(match_id), style=style, lang=lang)
    except ChronicleError as error:
        raise HTTPException(409, str(error)) from error
    if format == "markdown":
        return PlainTextResponse(to_markdown(story), media_type="text/markdown; charset=utf-8")
    return story
