"""Werewolf setup endpoints for the "new match" dialog: the role list and selection checks."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from games.werewolf.selection import (
    BalanceResult,
    Problem,
    Role,
    balance,
    fill_selection,
    load_roles,
    validate_selection,
)

router = APIRouter(prefix="/games/werewolf", tags=["werewolf"])


class SelectionRequest(BaseModel):
    roles: dict[str, int] = Field(description="Role id -> count; free seats become villagers")
    player_count: int


class SelectionReport(BaseModel):
    valid: bool
    problems: list[Problem]
    selection: dict[str, int] = Field(description="The roles with villagers filled in")
    balance: BalanceResult | None = Field(description="null while a role id is unknown")


@router.get("/roles")
def list_roles() -> list[Role]:
    """Every role that can be selected, with team, weight and whether it is unique."""
    return list(load_roles().values())


@router.post("/selection/validate")
def check_selection(request: SelectionRequest) -> SelectionReport:
    """Problems with a selection, its balance and the selection with free seats filled.

    Always answers 200; a selection that cannot be played has ``valid: false``
    and one problem per broken rule.
    """
    roles = load_roles()
    problems = validate_selection(request.roles, request.player_count, roles)
    filled = fill_selection(request.roles, request.player_count)
    known = all(role_id in roles for role_id in filled)
    return SelectionReport(
        valid=not problems,
        problems=problems,
        selection=filled,
        balance=balance(filled, roles) if known else None,
    )
