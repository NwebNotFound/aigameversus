"""GET /games/{id}/viewer-help: "Rules in 30 seconds" and a glossary for viewers."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from arena.api.live import LiveMatches
from arena.viewer_help import ViewerHelp, load_viewer_help

router = APIRouter(tags=["games"])


@router.get("/games/{game_id}/viewer-help")
def viewer_help(
    request: Request,
    game_id: str,
    lang: Annotated[Literal["en", "de"], Query(description="Language of the texts")] = "en",
) -> ViewerHelp:
    """Short rules and a glossary in plain words, for people who watch and have never played."""
    live: LiveMatches = request.app.state.live
    if game_id not in live.games:
        raise HTTPException(404, f"Unknown game {game_id!r}. Games: {', '.join(live.games)}")
    found = load_viewer_help(game_id, lang)
    if found is None:
        raise HTTPException(404, f"{game_id} has no viewer help in {lang} yet")
    return found
