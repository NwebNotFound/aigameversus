"""Werewolf setup endpoints for the "new match" dialog: roles, templates and selection checks."""

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from games.werewolf.selection import (
    BalanceResult,
    Problem,
    Role,
    apply_template,
    balance,
    fill_selection,
    load_roles,
    load_templates,
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


class TemplateOption(BaseModel):
    id: str
    name: str
    min_players: int
    random: bool = Field(description="Drawn from the match seed at the start")
    selection: dict[str, int] | None = Field(
        description="The roles for `players` players; null for a random template, or when the "
        "template does not fit that many players"
    )
    balance: BalanceResult | None


@router.get("/templates")
def list_templates(
    players: int = Query(ge=1, description="Players at the table"),
) -> list[TemplateOption]:
    """Every template, with the roles it gives at a table of `players`."""
    roles = load_roles()
    options = []
    for template in load_templates().values():
        selection = None
        if not template.random:
            try:
                selection = apply_template(template.id, players, roles=roles)
            except ValueError:
                selection = None  # too few or too many players for it
        options.append(
            TemplateOption(
                id=template.id,
                name=template.name,
                min_players=template.min_players,
                random=template.random,
                selection=selection,
                balance=balance(selection, roles) if selection else None,
            )
        )
    return options
