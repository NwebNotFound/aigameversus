"""The one call of a round, `submit_orders`: its schema and how its orders are carried out.

    run(state, data, ctx, {"p1": [order, ...], "p2": [...]})

The schema is the source of truth for the shape (docs/civ-interfaces.md, "The call").
It is flat on purpose: one object type with every field an order may have, so the
tool stays short in every prompt. What an order of a type needs is checked here, when
it runs: an order that is missing a field or breaks a rule is dropped with
`order_refused`, which only its nation sees, and the other orders go on.

Orders run type by type in `ORDER_TYPES` order (diplomacy, then cities, then armies),
and within a type nation by nation in seat order, so the log does not depend on who
answered first. Each order is checked again when its turn comes: an earlier one may
have spent the stock it needs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from arena.engine.plugin import TurnContext
from arena.engine.types import ToolSpec
from games.civ import armies, combat, diplomacy, economy
from games.civ.data_loader import CivData
from games.civ.state import CivState
from games.civ.world import Hex

MAX_ORDERS = 40
MAX_MESSAGES = 3  # message orders per nation and round
MAX_PROPOSALS = 3  # propose_treaty and propose_trade together
MAX_WORDS = 60  # in a message, and in the plan
PROPOSALS = ("propose_treaty", "propose_trade")

# The order in which the types run; also the enum of the schema.
ORDER_TYPES = (
    "message",
    "propose_treaty",
    "propose_trade",
    "respond",
    "declare_war",
    "break_treaty",
    "build",
    "demolish",
    "focus",
    "train",
    "disband",
    "split",
    "merge",
    "settle",
    "move",
    "fortify",
    "pillage",
)

# The fields an order of each type needs, as the player reads them in a refusal.
NEEDS: dict[str, tuple[str, ...]] = {
    "message": ("text",),
    "propose_treaty": ("to", "kind"),
    "propose_trade": ("to",),
    "respond": ("offer", "accept"),
    "declare_war": ("on",),
    "break_treaty": ("treaty",),
    "build": ("city", "building"),
    "demolish": ("city", "building"),
    "focus": ("city", "focus"),
    "train": ("city", "unit"),
    "disband": ("army",),
    "split": ("army", "units"),
    "merge": ("armies",),
    "settle": ("army",),
    "move": ("army", "to"),
    "fortify": ("army",),
    "pillage": ("army",),
}

_AMOUNTS = {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}}

SUBMIT_ORDERS = ToolSpec(
    name="submit_orders",
    description=(
        "All your orders for this round, in one call. Each order has a `type` and the "
        "fields of that type (see the rules). An order that breaks a rule is dropped and "
        "you read why next round; the others still run. `plan`: a short note to yourself, "
        "shown to you (and nobody else) next round."
    ),
    parameters={
        "type": "object",
        "properties": {
            "orders": {
                "type": "array",
                "maxItems": MAX_ORDERS,
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": list(ORDER_TYPES)},
                        "city": {"type": "string"},
                        "building": {"type": "string"},
                        "unit": {"type": "string"},
                        "count": {"type": "integer", "minimum": 1},
                        "focus": {"type": "string"},
                        "army": {"type": "string"},
                        "armies": {"type": "array", "items": {"type": "string"}},
                        "units": {"type": "array", "items": {"type": "string"}},
                        "to": {
                            "description": "move: a tile [col, row]; message, propose_*: a "
                            "nation (null in a message: everyone)",
                            "type": ["array", "string", "null"],
                        },
                        "text": {"type": "string"},
                        "kind": {"type": "string", "description": "the treaty"},
                        "rounds": {"type": "integer", "minimum": 1},
                        "payer": {"type": "string", "description": "tribute: who pays"},
                        "payment": _AMOUNTS,
                        "gives": _AMOUNTS,
                        "wants": _AMOUNTS,
                        "offer": {"type": "string"},
                        "accept": {"type": "boolean"},
                        "on": {"type": "string"},
                        "treaty": {"type": "string"},
                    },
                    "required": ["type"],
                    "additionalProperties": False,
                },
            },
            "plan": {"type": "string"},
        },
        "required": ["orders"],
        "additionalProperties": False,
    },
)


def plan_text(plan: Any) -> str | None:
    """The plan as it is kept: its first MAX_WORDS words, or None when there is none."""
    if not isinstance(plan, str) or not plan.split():
        return None
    return " ".join(plan.split()[:MAX_WORDS])


def run(
    state: CivState,
    data: CivData,
    ctx: TurnContext,
    orders: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    """Carry out the round's orders of every nation, type by type, nation by nation."""
    allowed = {nation: _within_limits(state, ctx, nation, orders[nation]) for nation in orders}
    for kind in ORDER_TYPES:
        for nation in state.nations:
            for order in allowed.get(nation, ()):
                if order.get("type") == kind:
                    problem = _missing(order) or _RUN[kind](state, data, ctx, nation, order)
                    if problem:
                        refuse(state, ctx, nation, order, problem)


def refuse(
    state: CivState, ctx: TurnContext, nation: str, order: Mapping[str, Any], reason: str
) -> None:
    ctx.emit(
        "order_refused",
        {"nation": nation, "round": state.round, "order": dict(order), "reason": reason},
        visible_to=[nation],
    )


def _within_limits(
    state: CivState, ctx: TurnContext, nation: str, orders: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    """The orders that stay within the limits of a round; the others are refused now."""
    kept, messages, proposals = [], 0, 0
    for order in orders:
        kind = order.get("type")
        if kind == "message":
            messages += 1
            if messages > MAX_MESSAGES:
                refuse(state, ctx, nation, order, f"At most {MAX_MESSAGES} messages a round.")
                continue
            words = len(str(order.get("text", "")).split())
            if words > MAX_WORDS:
                reason = f"A message has at most {MAX_WORDS} words; this one has {words}."
                refuse(state, ctx, nation, order, reason)
                continue
        if kind in PROPOSALS:
            proposals += 1
            if proposals > MAX_PROPOSALS:
                reason = f"At most {MAX_PROPOSALS} treaty and trade offers a round."
                refuse(state, ctx, nation, order, reason)
                continue
        kept.append(order)
    return kept


def _missing(order: Mapping[str, Any]) -> str | None:
    lacking = [field for field in NEEDS[order["type"]] if order.get(field) is None]
    if not lacking:
        return None
    needs = ", ".join(NEEDS[order["type"]])
    return f"A {order['type']} order needs {needs}; it has no {', '.join(lacking)}."


def _tile(value: Any) -> Hex | None:
    if (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(n, int) and not isinstance(n, bool) for n in value)
    ):
        return value[0], value[1]
    return None


def _nation(value: Any) -> str | None:
    return value if isinstance(value, str) else None


# --- one function per order type: it returns a problem, or carries the order out ----------
# Each checks with the system's own `*_problem` function, so the refusal is the message the
# system gives, and only then calls the order.

Order = Mapping[str, Any]


def _message(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    to = o.get("to")
    if to is not None and _nation(to) is None:
        return "A message goes to a nation id, or to null for everyone."
    text = str(o["text"])
    if problem := diplomacy.message_problem(state, nation, text, to):
        return problem
    diplomacy.message(state, ctx, nation, text, to)
    return None


def _propose_treaty(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    if (to := _nation(o["to"])) is None:
        return "propose_treaty goes to one nation: `to` is its id."
    args = (o["kind"], o.get("rounds"), o.get("payer"), o.get("payment"))
    if problem := diplomacy.treaty_problem(state, data, nation, to, *args):
        return problem
    diplomacy.propose_treaty(state, data, ctx, nation, to, *args)
    return None


def _propose_trade(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    if (to := _nation(o["to"])) is None:
        return "propose_trade goes to one nation: `to` is its id."
    gives, wants, rounds = o.get("gives") or {}, o.get("wants") or {}, o.get("rounds") or 1
    if problem := diplomacy.trade_problem(state, data, nation, to, gives, wants, rounds):
        return problem
    diplomacy.propose_trade(state, data, ctx, nation, to, gives, wants, rounds)
    return None


def _respond(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    offer = next((x for x in state.offers if x.id == o["offer"] and x.to == nation), None)
    kind = "trade" if offer is not None and offer.treaty is None else "treaty"
    accept = bool(o["accept"])
    if problem := diplomacy.answer_problem(state, data, nation, o["offer"], accept, kind):
        return problem
    answer = diplomacy.respond_trade if kind == "trade" else diplomacy.respond_treaty
    answer(state, data, ctx, nation, o["offer"], accept)
    return None


def _declare_war(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    if problem := diplomacy.war_problem(state, nation, o["on"]):
        return problem
    diplomacy.declare_war(state, data, ctx, nation, o["on"])
    return None


def _break_treaty(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    if problem := diplomacy.break_problem(state, nation, o["treaty"]):
        return problem
    diplomacy.break_treaty(state, data, ctx, nation, o["treaty"])
    return None


def _build(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    if problem := economy.build_problem(state, data, nation, o["city"], o["building"]):
        return problem
    economy.build(state, data, ctx, nation, o["city"], o["building"])
    return None


def _demolish(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    if problem := economy.demolish_problem(state, nation, o["city"], o["building"]):
        return problem
    economy.demolish(state, data, ctx, nation, o["city"], o["building"])
    return None


def _focus(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    if problem := economy.focus_problem(state, data, nation, o["city"], o["focus"]):
        return problem
    economy.set_focus(state, data, ctx, nation, o["city"], o["focus"])
    return None


def _train(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    count = o.get("count") or 1
    if problem := armies.train_problem(state, data, nation, o["city"], o["unit"], count):
        return problem
    armies.train(state, data, ctx, nation, o["city"], o["unit"], count)
    return None


def _disband(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    if problem := armies.disband_problem(state, nation, o["army"]):
        return problem
    armies.disband(state, ctx, nation, o["army"])
    return None


def _split(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    if problem := armies.split_problem(state, nation, o["army"], o["units"]):
        return problem
    armies.split(state, ctx, nation, o["army"], o["units"])
    return None


def _merge(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    if len(o["armies"]) < 2:
        return "merge needs at least two armies on one tile, for example ['a1', 'a2']."
    if problem := armies.merge_problem(state, data, nation, o["armies"]):
        return problem
    armies.merge(state, data, ctx, nation, o["armies"])
    return None


def _settle(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    if problem := armies.settle_problem(state, data, nation, o["army"]):
        return problem
    armies.settle(state, data, ctx, nation, o["army"])
    return None


def _move(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    """A move onto a tile that another nation holds is an attack on it (or refused)."""
    if (to := _tile(o["to"])) is None:
        return "`to` of a move is a tile [col, row], for example [4, 3]."
    if combat.holder(state, to, nation) is not None:
        if problem := combat.attack_problem(state, data, nation, o["army"], to):
            return problem
        combat.attack(state, data, ctx, nation, o["army"], to)
        return None
    if problem := armies.move_problem(state, data, nation, o["army"], to):
        return problem
    armies.move(state, data, ctx, nation, o["army"], to)
    return None


def _fortify(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    if problem := combat.fortify_problem(state, nation, o["army"]):
        return problem
    combat.fortify(state, ctx, nation, o["army"])
    return None


def _pillage(state: CivState, data: CivData, ctx: TurnContext, nation: str, o: Order):
    if problem := combat.pillage_problem(state, nation, o["army"]):
        return problem
    combat.pillage(state, data, ctx, nation, o["army"])
    return None


_RUN: dict[str, Callable[[CivState, CivData, TurnContext, str, Order], str | None]] = {
    "message": _message,
    "propose_treaty": _propose_treaty,
    "propose_trade": _propose_trade,
    "respond": _respond,
    "declare_war": _declare_war,
    "break_treaty": _break_treaty,
    "build": _build,
    "demolish": _demolish,
    "focus": _focus,
    "train": _train,
    "disband": _disband,
    "split": _split,
    "merge": _merge,
    "settle": _settle,
    "move": _move,
    "fortify": _fortify,
    "pillage": _pillage,
}
assert tuple(_RUN) == ORDER_TYPES
