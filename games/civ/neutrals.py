"""What neutral armies (barbarians) do in a round: after the nations' orders, before combat.

    act(state, data, ctx)

Each neutral army, in the order the armies were raised, attacks the nearest tile in its
reach that a nation holds with an army or a city; with none in reach it walks towards the
nearest city of a nation. It needs no random draw: the same state gives the same moves.
Rebel cities (neutral cities) stay where they are and do nothing.
"""

from __future__ import annotations

from collections.abc import Iterable

from arena.engine.plugin import TurnContext
from games.civ import armies, combat
from games.civ.data_loader import CivData
from games.civ.state import NEUTRAL, CivState
from games.civ.world import Hex, distance


def act(state: CivState, data: CivData, ctx: TurnContext) -> None:
    for army in [a for a in state.armies if a.owner == NEUTRAL]:
        if army.moved_in_round == state.round:
            continue
        ways = armies.reachable(state, data, army.id)
        targets = sorted(
            (distance(army.tile, tile), tile)
            for tile in ways
            if combat.holder(state, tile, NEUTRAL) is not None
        )
        for _, tile in targets:
            if combat.attack_problem(state, data, NEUTRAL, army.id, tile) is None:
                combat.attack(state, data, ctx, NEUTRAL, army.id, tile)
                break
        else:
            _walk(state, data, ctx, army.id, ways)


def _walk(
    state: CivState, data: CivData, ctx: TurnContext, army_id: str, ways: Iterable[Hex]
) -> None:
    army = state.army(army_id)
    cities = [c.tile for c in state.cities if c.owner != NEUTRAL]
    ways = [tile for tile in ways if combat.holder(state, tile, NEUTRAL) is None]
    if not cities or not ways:
        return
    goal = min(cities, key=lambda tile: (distance(army.tile, tile), tile))
    best = min(ways, key=lambda tile: (distance(tile, goal), tile))
    if distance(best, goal) < distance(army.tile, goal):
        armies.move(state, data, ctx, NEUTRAL, army_id, best)
