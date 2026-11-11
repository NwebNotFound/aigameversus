"""Role abilities: the code behind the hook names in `roles/*.yaml`.

A role file names its handlers, for example `on_night: seer_inspect`. Night
handlers are `NightAbility` classes registered in `NIGHT`; passive hooks
(`on_death: hunter_shoot`) are handled by the plugin by name. A role whose
handler is not registered here cannot be put in a match yet.

Abilities only decide: their `apply` emits events, and the plugin's
`apply_event` changes the state.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from arena.engine.plugin import TurnContext
from arena.engine.types import Action, PlayerId, ToolSpec

if TYPE_CHECKING:
    from games.werewolf.plugin import WerewolfState


def target_schema(choices: Sequence[PlayerId | None], description: str) -> dict[str, Any]:
    """A JSON-schema property allowing exactly these targets (None = nobody)."""
    allowed = list(choices)
    kinds = ["string", "null"] if None in allowed else "string"
    return {"type": kinds, "enum": allowed, "description": description}


def tool(name: str, description: str, properties: dict[str, Any], required=()) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": properties,
            "required": list(required),
            "additionalProperties": False,
        },
    )


class NightAbility:
    """What a role does at night: who acts, which tool, what it causes."""

    handler: ClassVar[str]
    sub_order: ClassVar[int] = 0  # order among roles with the same night_order

    def acts_tonight(self, state: "WerewolfState", player: PlayerId) -> bool:
        return True

    def tools(self, state: "WerewolfState", player: PlayerId) -> list[ToolSpec]:
        raise NotImplementedError

    def validate(self, state: "WerewolfState", player: PlayerId, action: Action) -> str | None:
        return None

    def apply(
        self, state: "WerewolfState", player: PlayerId, action: Action, ctx: TurnContext
    ) -> None:
        raise NotImplementedError


class SeerInspect(NightAbility):
    handler = "seer_inspect"

    def tools(self, state, player):
        others = [p for p in state.alive if p != player]
        return [
            tool(
                "seer_check",
                "Learn the role of one living player. Only you see the answer.",
                {"target": target_schema(others, "The player to check.")},
                required=["target"],
            )
        ]

    def apply(self, state, player, action, ctx):
        target = action.arguments["target"]
        ctx.emit(
            "seer_inspected",
            {"player": player, "target": target, "role": state.roles[target]},
            visible_to=[player],
        )


class WitchPotions(NightAbility):
    """One healing potion and one poison per match; she sees the wolves' victim."""

    handler = "witch_potions"

    def tools(self, state, player):
        victim = state.wolf_victim()
        can_heal = state.potions["heal"] and victim is not None
        poisonable = (
            [None] + [p for p in state.alive if p != player] if state.potions["poison"] else [None]
        )
        heal_note = (
            f"The wolves chose {victim}. Heal them with your one healing potion?"
            if victim
            else "Nobody was attacked, or your healing potion is used up."
        )
        return [
            tool(
                "witch_act",
                f"{heal_note} You may also poison one player (once per match), or nobody.",
                {
                    "heal": {"type": "boolean", "enum": [False, True] if can_heal else [False]},
                    "poison_target": target_schema(poisonable, "Who to poison, or null."),
                },
                required=["heal", "poison_target"],
            )
        ]

    def apply(self, state, player, action, ctx):
        heal = bool(action.arguments["heal"])
        ctx.emit(
            "witch_acted",
            {
                "player": player,
                "healed": state.wolf_victim() if heal else None,
                "poisoned": action.arguments["poison_target"],
            },
            visible_to=[player],
        )


class WolvesChooseVictim(NightAbility):
    """Marker for the werewolf role: the pack's vote is a plugin step for every pack member."""

    handler = "wolves_choose_victim"

    def acts_tonight(self, state, player):
        return False


class CupidLinkLovers(NightAbility):
    """Night 1 only (role file): two players fall in love; each learns the other."""

    handler = "cupid_link_lovers"

    def tools(self, state, player):
        living = list(state.alive)
        return [
            tool(
                "link_lovers",
                "Make two living players lovers (you may pick yourself). If one dies, "
                "the other dies of grief. Only they and you learn it.",
                {
                    "a": target_schema(living, "The first lover."),
                    "b": target_schema(living, "The second lover."),
                },
                required=["a", "b"],
            )
        ]

    def validate(self, state, player, action):
        if action.arguments["a"] == action.arguments["b"]:
            return "Pick two different players as lovers."
        return None

    def apply(self, state, player, action, ctx):
        lovers = [action.arguments["a"], action.arguments["b"]]
        ctx.emit("lovers_linked", {"player": player, "lovers": lovers}, visible_to=[player])
        ctx.emit("love_revealed", {"lovers": lovers}, visible_to=lovers)


class ProtectorGuard(NightAbility):
    """Protects one player from the wolves; never the same player two nights in a row."""

    handler = "protector_guard"

    def tools(self, state, player):
        choices = [p for p in state.alive if p != state.last_protected]
        return [
            tool(
                "protect",
                "Protect one living player from the wolves tonight (yourself allowed, "
                "not the same player as last night).",
                {"target": target_schema(choices, "The player to protect.")},
                required=["target"],
            )
        ]

    def apply(self, state, player, action, ctx):
        target = action.arguments["target"]
        ctx.emit("protected", {"player": player, "target": target}, visible_to=[player])


SPY_FIND_CHANCE = 0.30
SPY_CAUGHT_CHANCE = 0.15


class LittleGirlSpy(NightAbility):
    """May spy on the wolves: 30 % to learn one wolf, 15 % to be caught and eaten instead."""

    handler = "little_girl_spy"

    def tools(self, state, player):
        return [
            tool(
                "spy",
                "Peek at the wolves: 30 % chance to learn one of them, but 15 % chance "
                "they catch you and eat you instead of their victim.",
                {},
            ),
            tool("stay_in_bed", "Do not spy tonight.", {}),
        ]

    def apply(self, state, player, action, ctx):
        if action.tool != "spy":
            return
        rng = ctx.rng("spy", state.night)
        found = rng.random() < SPY_FIND_CHANCE
        caught = rng.random() < SPY_CAUGHT_CHANCE
        wolves = sorted(p for p in state.alive if p in state.pack)
        wolf = rng.choice(wolves) if found and wolves else None
        ctx.emit("spied", {"player": player, "wolf": wolf}, visible_to=[player])
        if caught:
            ctx.emit("girl_caught", {"player": player}, visible_to=[])


NIGHT: dict[str, NightAbility] = {
    ability.handler: ability
    for ability in (
        SeerInspect(),
        WitchPotions(),
        WolvesChooseVictim(),
        CupidLinkLovers(),
        ProtectorGuard(),
        LittleGirlSpy(),
    )
}

# Passive hooks the plugin implements by name.
PASSIVE = {
    "hunter_shoot",
    "lover_dies_of_grief",
    "elder_survives_first",
    "elder_strips_powers",
    "idiot_survives",
    "scapegoat_dies",
}


def implemented(handler: str) -> bool:
    return handler in NIGHT or handler in PASSIVE
