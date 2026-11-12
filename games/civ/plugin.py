"""Throne of Tokens: four to six nations on a hex map, one round per engine turn.

Every round all nations act at once with one `submit_orders` call each
(docs/civ-interfaces.md). The plugin opens a round, takes the calls, then closes
the round and opens the next (`turn.py` has the steps). The rules live in the
modules of this package; the plugin wires them to the engine, builds what a
nation sees (`get_observation`, with the public `scoreboard`) and what
spectators see (`render_spec`, and `render_spec_for` as one nation sees it).
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from arena.engine.plugin import GamePlugin, TurnContext
from arena.engine.types import Action, Event, Placement, PlayerId, ToolSpec, TurnMode
from games.civ import (
    armies,
    combat,
    diplomacy,
    economy,
    observation,
    orders,
    prompt,
    turn,
    victory,
)
from games.civ.bot import random_orders
from games.civ.data_loader import CivData, load_civ_data
from games.civ.state import NEUTRAL, CivState, new_game
from games.civ.world import generate_map

DATA = load_civ_data()


class CivGame(GamePlugin[CivState]):
    id = "civ"
    name = "Throne of Tokens"
    version = "1"
    min_players = DATA.balance.map.nations.min
    max_players = DATA.balance.map.nations.max
    turn_mode = TurnMode.SIMULTANEOUS
    max_turns = DATA.victory.round_limit.rounds + 1  # one turn per round; the limit ends it

    data: CivData = DATA

    def prompt_version(self, settings: Mapping[str, Any] | None = None) -> str:
        """The prompt version of a match, recorded with it (see `prompt.py`)."""
        return prompt.version_of(settings)

    def situation_summary(
        self, observation: Mapping[str, Any], settings: Mapping[str, Any] | None = None
    ) -> str | None:
        """A short text for the top of the turn's prompt; only version civ-p2 has one."""
        if prompt.version_of(settings) == "civ-p1":
            return None
        return prompt.situation_summary(observation)

    def rules(self, settings: Mapping[str, Any] | None = None) -> str:
        """rules.md and what the settings add, with this match's round limit where it is named."""
        text = prompt.rules_text(settings)
        rounds = (settings or {}).get("rounds")
        if rounds is None:
            return text
        default = f"After round {self.data.victory.round_limit.rounds},"
        return text.replace(default, f"After round {rounds},")

    def initial_state(self, players: Sequence[PlayerId], settings: Mapping[str, Any]) -> CivState:
        known = {"rounds", *prompt.SETTINGS}
        unknown = set(settings) - known
        if unknown:
            raise ValueError(
                f"Unknown settings for civ: {sorted(unknown)}; known: {', '.join(sorted(known))}"
            )
        prompt.check(settings)  # refuses a value the prompt does not know
        rounds = settings.get("rounds")
        most = self.data.victory.round_limit.rounds
        if rounds is not None and (
            not isinstance(rounds, int) or isinstance(rounds, bool) or not 1 <= rounds <= most
        ):
            raise ValueError(f"rounds must be a whole number from 1 to {most}, not {rounds!r}")
        if not self.min_players <= len(players) <= self.max_players:
            raise ValueError(
                f"Throne of Tokens is for {self.min_players} to {self.max_players} nations"
            )
        if NEUTRAL in players:
            raise ValueError(f"'{NEUTRAL}' is the owner of barbarians, not a seat")
        return new_game(players, self.data, rounds, prompt.plan_of(settings) == "on")

    def setup(self, state: CivState, ctx: TurnContext) -> None:
        world = generate_map(list(state.nations), self.data, ctx.rng("map"))
        # The whole map is for spectators; a nation sees it through its fog.
        ctx.emit(
            "map_drawn",
            {"rows": world.rows, "starts": [start.model_dump() for start in world.starts]},
            visible_to=[],
        )
        for start in state.world.starts:
            economy.found_city(state, ctx, start.player, start.tile)
        armies.deploy_start_units(state, self.data, ctx)
        turn.open_round(state, self.data, ctx)

    def active_players(self, state: CivState) -> list[PlayerId]:
        if state.victory is not None:
            return []
        return [nation for nation in state.nations if _alive(state, nation)]

    def get_observation(self, state: CivState, player: PlayerId) -> dict[str, Any]:
        data, nation = self.data, state.nations[player]
        extras = {
            "reputation": nation.reputation,
            "production_modifier": round(1 + economy.production_modifier(state, data, player), 2),
            "gold_held_rounds": state.rich_rounds.get(player, 0),
            "relations": _relations(state, player),
            "offers": _offers(state, player),
            "refused": [
                {"order": r["order"], "reason": r["reason"]}
                for r in state.refused
                if r["nation"] == player and r["round"] == state.round - 1
            ],
        }
        board = scoreboard(state, data)
        seen = observation.observe(
            state,
            data,
            player,
            scoreboard=board,
            extras=extras,
            plan=nation.plan if state.private_plan else None,
        )
        seen["legal"]["orders"] = _order_targets(state, data, player, seen)
        seen["scoreboard"] = board
        return seen

    def get_tools(self, state: CivState, player: PlayerId) -> list[ToolSpec]:
        return [orders.submit_orders(state.private_plan)]

    def validate(self, state: CivState, player: PlayerId, action: Action) -> str | None:
        # The schema has checked the shape; a single bad order is dropped when it runs.
        return None

    def apply_actions(
        self, state: CivState, actions: Mapping[PlayerId, Action], ctx: TurnContext
    ) -> None:
        for nation in state.nations:
            if nation not in actions:
                continue
            plan = orders.plan_text(actions[nation].arguments.get("plan"))
            if plan != state.nations[nation].plan:
                ctx.emit("plan_set", {"nation": nation, "plan": plan}, visible_to=[nation])
        given = {
            nation: list(action.arguments.get("orders", [])) for nation, action in actions.items()
        }
        self._next_round(state, ctx, given)

    def step(self, state: CivState, ctx: TurnContext) -> None:
        # A round with no nation left to ask (only barbarians and rebels) still runs.
        if state.victory is None and not self.active_players(state):
            self._next_round(state, ctx, {})

    def _next_round(
        self, state: CivState, ctx: TurnContext, given: Mapping[str, list[dict[str, Any]]]
    ) -> None:
        turn.close_round(state, self.data, ctx, given)
        if state.victory is None:
            turn.open_round(state, self.data, ctx)

    def apply_event(self, state: CivState, event: Event) -> None:
        turn.apply_event(state, event)

    def is_over(self, state: CivState) -> bool:
        return state.victory is not None

    def results(self, state: CivState) -> list[Placement]:
        return [Placement(player=p["player"], rank=p["rank"]) for p in state.victory["placements"]]

    def random_action(
        self, observation: Mapping[str, Any], tools: Sequence[ToolSpec], rng: random.Random
    ) -> Action:
        return Action(tool="submit_orders", arguments=random_orders(dict(observation), rng))

    # --- the board ------------------------------------------------------------------

    def render_spec(self, state: CivState) -> dict[str, Any]:
        """The whole board, every nation's fog included: for the Spectator view only."""
        data = self.data
        return {
            "layout": "hex_map",
            "round": state.round,
            "rounds_total": victory.round_limit(state, data),
            "cols": len(state.world.rows[0]) if state.world.rows else 0,
            "rows": len(state.world.rows),
            "terrain": ["".join(observation.glyph(t) for t in row) for row in state.world.rows],
            "legend": {observation.glyph(kind): kind for kind in data.terrain},
            "cities": [_city_spec(state, city) for city in state.cities],
            "armies": [_army_spec(state, data, army, units=True) for army in state.armies],
            "nations": [_nation_spec(state, nation, stock=True) for nation in state.nations],
            "treaties": [{"kind": p.kind, "parties": list(p.parties)} for p in state.treaties],
            "wars": [list(pair) for pair in state.wars],
            "fog": {nation: _fog_rows(state, data, nation) for nation in state.nations},
            "battles": _battles(state),
        }

    def render_spec_for(self, state: CivState, nation: PlayerId) -> dict[str, Any]:
        """The board as one nation sees it: the spoiler-free view (the allowlist of the doc)."""
        data = self.data
        seen = observation.visible_to(state, data, nation)
        full = self.render_spec(state)
        return {
            **{key: full[key] for key in ("layout", "round", "rounds_total", "cols", "rows")},
            "terrain": full["terrain"],
            "legend": full["legend"],
            "cities": [_city_spec(state, c) for c in state.cities if c.tile in seen],
            "armies": [
                _army_spec(state, data, a, units=a.owner == nation)
                for a in state.armies
                if a.tile in seen
            ],
            "nations": [_nation_spec(state, n, stock=n == nation) for n in state.nations],
            "treaties": full["treaties"],
            "wars": full["wars"],
            "fog": {nation: full["fog"][nation]},
            "battles": [
                b for b in _battles(state) if nation in b["nations"] or tuple(b["tile"]) in seen
            ],
        }


def scoreboard(state: CivState, data: CivData) -> dict[str, Any]:
    """What every nation may know of every other (D-128), built from the state alone.

    No scores and no gold: a round-limit score holds a nation's gold and population.
    """
    total = len(state.cities)
    held = {nation: sum(1 for c in state.cities if c.owner == nation) for nation in state.nations}
    economy_rules = data.victory.economy
    holding = [n for n in state.nations if state.rich_rounds.get(n, 0) > 0]
    leader = max(holding, key=lambda n: state.rich_rounds[n], default=None)
    return {
        "round": state.round,
        "cities_total": total,
        "cities": held,
        "domination_needed": max(1, math.ceil(data.victory.domination.city_share * total - 1e-9)),
        "gold_countdown": None
        if leader is None
        else {
            "nation": leader,
            "rounds_held": state.rich_rounds[leader],
            "rounds_needed": economy_rules.hold_rounds,
        },
        "reputation": {nation: n.reputation for nation, n in state.nations.items()},
    }


def _alive(state: CivState, nation: str) -> bool:
    return any(c.owner == nation for c in state.cities) or any(
        a.owner == nation for a in state.armies
    )


def _relations(state: CivState, player: str) -> dict[str, Any]:
    """Treaties and wars are public; a treaty shows its kind, parties and end."""
    return {
        "treaties": [
            {"id": p.id, "kind": p.kind, "parties": list(p.parties), "ends_round": p.ends_round}
            for p in state.treaties
        ],
        "wars": [list(pair) for pair in state.wars],
        "at_war_with": diplomacy.wars_of(state, player),
    }


def _offers(state: CivState, player: str) -> list[dict[str, Any]]:
    """The offers the nation may answer this round."""
    shown = []
    for offer in state.offers:
        if offer.to != player:
            continue
        item: dict[str, Any] = {"id": offer.id, "from": offer.sender, "rounds": offer.rounds}
        if offer.treaty is not None:
            item["treaty"] = offer.treaty
            if offer.payer is not None:
                item |= {"payer": offer.payer, "payment": dict(offer.payment)}
        else:
            item |= {"gives": dict(offer.gives), "wants": dict(offer.wants)}
        shown.append(item)
    return shown


def _order_targets(
    state: CivState, data: CivData, player: str, seen: Mapping[str, Any]
) -> dict[str, str]:
    """The order types that can do something now, each with its fields and, where only some
    cities, armies or nations qualify, which ones."""
    legal = seen["legal"]["cities"]
    mine = [a for a in state.armies if a.owner == player]
    others = [n for n in state.nations if n != player]
    at_peace = [n for n in others if not diplomacy.at_war(state, player, n)]
    tiles = Counter(a.tile for a in mine)
    pillage = [a.id for a in mine if combat.pillage_problem(state, player, a.id) is None]

    def ids(fields: str, chosen: Sequence[Any]) -> str | None:
        return f"{fields}; for: {', '.join(map(str, chosen))}" if chosen else None

    found = {
        "build": ids("city, building (legal.cities)", [c for c, x in legal.items() if x["build"]]),
        "train": ids(
            "city, unit, count (legal.cities)", [c for c, x in legal.items() if x["train"]]
        ),
        "demolish": ids("city, building", [c["id"] for c in seen["cities"] if c["buildings"]]),
        "focus": "city, focus (growth, production, military)" if seen["cities"] else None,
        "move": "army, to (a tile of its reachable; a tile held by a nation you are at war "
        "with, or by barbarians, is attacked)"
        if any(a["reachable"] for a in seen["armies"])
        else None,
        "fortify": "army" if mine else None,
        "pillage": ids("army", pillage),
        "settle": ids("army", [a["id"] for a in seen["armies"] if a["can_settle"]]),
        "split": "army, units" if any(len(a.units) > 1 for a in mine) else None,
        "merge": "armies (on one tile)" if any(n > 1 for n in tiles.values()) else None,
        "disband": "army" if mine else None,
        "message": "to (a nation, or null for all), text",
        "propose_treaty": "to, kind, rounds; tribute: payer, payment",
        "propose_trade": ids("to, gives, wants, rounds", at_peace),
        "respond": ids("offer, accept", [o["id"] for o in seen["offers"]]),
        "declare_war": ids("on", at_peace),
        "break_treaty": ids("treaty", [p.id for p in state.treaties if player in p.parties]),
    }
    return {kind: text for kind, text in found.items() if text}


def _city_spec(state: CivState, city) -> dict[str, Any]:
    start = next((s for s in state.world.starts if s.player == city.owner), None)
    return {
        "id": city.id,
        "owner": city.owner,
        "tile": [city.col, city.row],
        "population": city.population,
        "capital": start is not None and start.tile == city.tile,
        "walls": "wall" in city.buildings,
    }


def _army_spec(state: CivState, data: CivData, army, *, units: bool) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "id": army.id,
        "owner": army.owner,
        "tile": [army.col, army.row],
        "strength": combat.strength(data, army.units),
    }
    if units:
        spec["units"] = dict(Counter(troop.kind for troop in army.units))
        spec["fortified"] = army.fortified_from is not None and army.fortified_from <= state.round
    return spec


def _nation_spec(state: CivState, nation: str, *, stock: bool) -> dict[str, Any]:
    spec: dict[str, Any] = {"id": nation}
    if stock:
        spec["stock"] = dict(state.nations[nation].stock)
    return spec | {
        "reputation": state.nations[nation].reputation,
        "cities": sum(1 for c in state.cities if c.owner == nation),
        "at_war": diplomacy.wars_of(state, nation),
    }


def _fog_rows(state: CivState, data: CivData, nation: str) -> list[str]:
    seen = observation.visible_to(state, data, nation)
    return [
        "".join("1" if (col, row) in seen else "0" for col in range(len(line)))
        for row, line in enumerate(state.world.rows)
    ]


def _battles(state: CivState) -> list[dict[str, Any]]:
    """The battles of the round resolved last, as the board marks them."""
    resolved = state.round if state.victory is not None else state.round - 1
    return [dict(b) for b in state.battles if b["round"] == resolved]
