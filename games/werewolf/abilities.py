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


NIGHT: dict[str, NightAbility] = {
    ability.handler: ability for ability in (SeerInspect(), WitchPotions(), WolvesChooseVictim())
}

# Passive hooks the plugin implements by name.
PASSIVE = {"hunter_shoot"}


def implemented(handler: str) -> bool:
    return handler in NIGHT or handler in PASSIVE
