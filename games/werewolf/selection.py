"""Werewolf role selection: check a chosen mix, rate its balance, apply templates, deal roles.

A *selection* maps role ids to counts, for example ``{"werewolf": 2, "seer": 1}``.
Free seats are filled with villagers.

    roles = load_roles()
    problems = validate_selection({"werewolf": 2, "seer": 1}, 8, roles)
    filled = fill_selection({"werewolf": 2, "seer": 1}, 8)  # + 5 villagers
    balance(filled, roles).verdict                          # "even"

Pure functions over the YAML data in ``roles/`` and ``templates.yaml``; no game logic.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from jsonschema import ValidationError, validate
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).parent
MIN_PLAYERS = 6
MAX_PLAYERS = 16
FILL_ROLE = "villager"

# Balance verdict: a total within +-EVEN_MARGIN is even, i.e. less than one werewolf's
# weight (6) away from 0 (D-022).
EVEN_MARGIN = 5
# Random mixes the "random_balanced" template draws before keeping the most even one.
RANDOM_CANDIDATES = 300

Selection = dict[str, int]
Team = Literal["village", "wolves", "solo"]
ProblemCode = Literal[
    "unknown_role",
    "invalid_count",
    "too_few_players",
    "too_many_players",
    "too_many_roles",
    "unique_role_repeated",
    "no_wolf",
    "too_many_wolves",
]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class Role(_Model):
    id: str
    name: str
    team: Team
    unique: bool
    weight: int
    night_order: int | None
    first_night_only: bool = False
    description: str

    @property
    def hunts_with_wolves(self) -> bool:
        """Wolves and the solo White Werewolf both count as wolves for selection rules."""
        return self.team in ("wolves", "solo")


class Problem(_Model):
    code: ProblemCode
    message: str
    role: str | None = None


class BalanceResult(_Model):
    total: int
    verdict: Literal["village", "even", "wolves"]


class Template(_Model):
    id: str
    name: str
    min_players: int
    roles: dict[str, int | Literal["fill"]] = {}
    random: bool = False
    target_balance: int = 0


@cache
def load_roles(roles_dir: Path = ROOT / "roles") -> dict[str, Role]:
    """Every role in ``roles_dir``, checked against ``role.schema.json``, keyed by id."""
    schema = json.loads((roles_dir / "role.schema.json").read_text(encoding="utf-8"))
    roles: dict[str, Role] = {}
    for path in sorted(roles_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            validate(data, schema)
        except ValidationError as exc:
            raise ValueError(f"{path}: {exc.message}") from None
        if data["id"] != path.stem:
            raise ValueError(f"{path}: id '{data['id']}' must match the file name")
        roles[data["id"]] = Role.model_validate(
            {key: data[key] for key in Role.model_fields if key in data}
        )
    if FILL_ROLE not in roles:
        raise ValueError(f"{roles_dir}: the fill role '{FILL_ROLE}' is missing")
    return roles


@cache
def load_templates(path: Path = ROOT / "templates.yaml") -> dict[str, Template]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {t["id"]: Template.model_validate(t) for t in data["templates"]}


def fill_selection(selection: Mapping[str, int], player_count: int) -> Selection:
    """The selection plus villagers for every free seat; roles with count 0 are dropped."""
    filled = {role: count for role, count in selection.items() if count != 0}
    free = player_count - sum(filled.values())
    if free > 0:
        filled[FILL_ROLE] = filled.get(FILL_ROLE, 0) + free
    return filled


def validate_selection(
    selection: Mapping[str, int], player_count: int, roles: Mapping[str, Role] | None = None
) -> list[Problem]:
    """Everything wrong with a selection for ``player_count`` players; empty when it is playable.

    Rules from the spec: 6-16 players, at least 1 wolf, wolves fewer than half
    the players, unique roles at most once, not more roles than players. Free
    seats count as villagers.
    """
    roles = load_roles() if roles is None else roles
    problems: list[Problem] = []

    if player_count < MIN_PLAYERS:
        message = f"Werewolf needs at least {MIN_PLAYERS} players, got {player_count}"
        problems.append(_problem("too_few_players", message))
    if player_count > MAX_PLAYERS:
        message = f"Werewolf allows at most {MAX_PLAYERS} players, got {player_count}"
        problems.append(_problem("too_many_players", message))

    known: Selection = {}
    for role_id, count in selection.items():
        if role_id not in roles:
            problems.append(_problem("unknown_role", f"'{role_id}' is not a role", role=role_id))
        elif not isinstance(count, int) or isinstance(count, bool) or count < 0:
            name = roles[role_id].name
            message = f"{name}: count must be a whole number of 0 or more, got {count!r}"
            problems.append(_problem("invalid_count", message, role=role_id))
        elif count > 0:
            known[role_id] = count

    for role_id, count in known.items():
        role = roles[role_id]
        if role.unique and count > 1:
            message = f"{role.name} may appear only once, selected {count} times"
            problems.append(_problem("unique_role_repeated", message, role=role_id))

    chosen = sum(known.values())
    if chosen > player_count:
        message = (
            f"{chosen} roles chosen for {player_count} players; remove {chosen - player_count}"
        )
        problems.append(_problem("too_many_roles", message))

    wolves = sum(count for role_id, count in known.items() if roles[role_id].hunts_with_wolves)
    if wolves == 0:
        problems.append(_problem("no_wolf", "add at least one wolf"))
    elif wolves * 2 >= player_count:
        message = (
            f"{wolves} wolves for {player_count} players; wolves must be fewer than half "
            f"(at most {(player_count - 1) // 2})"
        )
        problems.append(_problem("too_many_wolves", message))
    return problems


def balance(selection: Mapping[str, int], roles: Mapping[str, Role] | None = None) -> BalanceResult:
    """Sum of role weights times counts. Positive favours the village, negative the wolves."""
    roles = load_roles() if roles is None else roles
    total = sum(roles[role_id].weight * count for role_id, count in selection.items())
    if total > EVEN_MARGIN:
        verdict: Literal["village", "even", "wolves"] = "village"
    elif total < -EVEN_MARGIN:
        verdict = "wolves"
    else:
        verdict = "even"
    return BalanceResult(total=total, verdict=verdict)


def apply_template(
    template_id: str,
    player_count: int,
    rng: random.Random | None = None,
    roles: Mapping[str, Role] | None = None,
) -> Selection:
    """The filled selection a template gives for ``player_count`` players.

    ``random_balanced`` needs ``rng`` (a stream from the match seed) and returns
    the most even of several random playable mixes; the same seed gives the same mix.
    """
    roles = load_roles() if roles is None else roles
    templates = load_templates()
    if template_id not in templates:
        raise ValueError(f"unknown template '{template_id}' (known: {', '.join(templates)})")
    template = templates[template_id]
    if not max(MIN_PLAYERS, template.min_players) <= player_count <= MAX_PLAYERS:
        raise ValueError(
            f"template '{template_id}' needs {max(MIN_PLAYERS, template.min_players)}"
            f"-{MAX_PLAYERS} players, got {player_count}"
        )
    if not template.random:
        fixed = {role: n for role, n in template.roles.items() if isinstance(n, int)}
        return fill_selection(fixed, player_count)
    if rng is None:
        raise ValueError(f"template '{template_id}' is random and needs an rng")

    best: Selection | None = None
    best_distance = 0
    for _ in range(RANDOM_CANDIDATES):
        candidate = _random_mix(player_count, rng, roles)
        if validate_selection(candidate, player_count, roles):
            continue
        distance = abs(balance(candidate, roles).total - template.target_balance)
        if best is None or distance < best_distance:
            best, best_distance = candidate, distance
    if best is None:
        raise ValueError(f"no playable random mix found for {player_count} players")
    return best


def assign_roles[P](
    selection: Mapping[str, int],
    players: Sequence[P],
    rng: random.Random,
    roles: Mapping[str, Role] | None = None,
) -> dict[P, str]:
    """Deal the filled selection to ``players`` at random; the same rng gives the same deal."""
    filled = fill_selection(selection, len(players))
    problems = validate_selection(filled, len(players), roles)
    if problems:
        raise ValueError("; ".join(problem.message for problem in problems))
    if len(set(players)) != len(players):
        raise ValueError("players must be distinct")
    deck = [role_id for role_id in sorted(filled) for _ in range(filled[role_id])]
    rng.shuffle(deck)
    return dict(zip(players, deck, strict=True))


def _random_mix(player_count: int, rng: random.Random, roles: Mapping[str, Role]) -> Selection:
    """One random mix: a wolf count, some special roles on both sides, villagers for the rest."""
    wolf_specials = sorted(r for r, role in roles.items() if role.unique and role.hunts_with_wolves)
    village_specials = sorted(
        r for r, role in roles.items() if role.unique and not role.hunts_with_wolves
    )
    wolves = rng.randint(1, (player_count - 1) // 2)
    rng.shuffle(wolf_specials)
    rng.shuffle(village_specials)
    mix: Selection = dict.fromkeys(
        wolf_specials[: rng.randint(0, min(len(wolf_specials), wolves))], 1
    )
    mix["werewolf"] = wolves - len(mix)
    seats = player_count - wolves
    mix.update(
        dict.fromkeys(village_specials[: rng.randint(0, min(len(village_specials), seats))], 1)
    )
    return fill_selection(mix, player_count)


def _problem(code: ProblemCode, message: str, role: str | None = None) -> Problem:
    return Problem(code=code, message=message, role=role)
