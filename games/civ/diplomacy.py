"""Diplomacy in Throne of Tokens: messages, treaties, wars, reputation and trade.

Like the other systems, every change is an event and only the functions in
``APPLIERS`` touch the state. Who sees what:

- An offer, its answer, a trade and a tribute payment are private to the two
  nations.
- A signed, broken or expired treaty and a declared war are public: the world
  knows who is allied with whom, and a broken word costs reputation in front
  of everyone.
- A message is the engine's ``message`` event, public or private to the two.

Its part of a round (``turn.py`` has the whole order):

    expire(state, ctx)  # at the start: last round's open offers and ended treaties go
    # diplomacy phase: message, propose_treaty, respond_treaty, propose_trade,
    #                  respond_trade, break_treaty, declare_war
    settle(state, data, ctx)  # the trade step: tributes and agreed trades are carried out

Combat and the turn flow ask ``at_war``, ``may_attack``, ``allies``,
``open_borders`` and ``wars_of``. All numbers come from ``data/treaties.yaml``
and ``trade`` in ``data/balance.yaml``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, get_args

from arena.engine.plugin import TurnContext
from arena.engine.types import MESSAGE
from games.civ.data_loader import CivData, Resource
from games.civ.economy import must_be_legal
from games.civ.state import CivState, Deal, Offer, Pact

RESOURCES: tuple[Resource, ...] = get_args(Resource)
MESSAGE_CHARS = 600  # the longest message a nation may send


# --- questions --------------------------------------------------------------


def pair(a: str, b: str) -> list[str]:
    return sorted([a, b])


def at_war(state: CivState, a: str, b: str) -> bool:
    return pair(a, b) in state.wars


def wars_of(state: CivState, player: str) -> list[str]:
    """The nations this one is at war with, sorted."""
    return sorted(other for war in state.wars if player in war for other in war if other != player)


def treaties_between(state: CivState, a: str, b: str) -> list[Pact]:
    return [pact for pact in state.treaties if pact.parties == pair(a, b)]


def may_attack(state: CivState, data: CivData, attacker: str, target: str) -> str | None:
    """None if no treaty forbids the attack, otherwise a message naming the treaty.

    Whether an attack also needs a declared war is the combat rule's to decide.
    """
    for pact in treaties_between(state, attacker, target):
        if data.treaties[pact.kind].forbids_attack:
            return (
                f"Your {data.treaties[pact.kind].name} with {target} ({pact.id}) forbids an "
                f"attack. Break it with break_treaty or declare war first."
            )
    return None


def allies(state: CivState, data: CivData, player: str) -> list[str]:
    """The nations this one shares its sight with: its partners in an alliance, sorted."""
    return sorted(
        other
        for pact in state.treaties
        if player in pact.parties and data.treaties[pact.kind].shared_vision
        for other in pact.parties
        if other != player
    )


def open_borders(state: CivState, data: CivData, a: str, b: str) -> bool:
    """Whether the armies of either may pass through the land of the other."""
    return any(data.treaties[pact.kind].open_borders for pact in treaties_between(state, a, b))


def trade_fee(state: CivState, data: CivData, player: str) -> Decimal:
    """The share of what a nation hands over in a trade that it pays on top as a fee.

    The base fee, more below the reputation limit, less with a market: only the
    nation's best market counts, as with granaries.
    """
    rules = data.balance.trade
    fee = Decimal(str(rules.base_fee))
    if state.nations[player].reputation < rules.low_reputation_below:
        fee += Decimal(str(rules.low_reputation_extra_fee))
    best = min(
        (
            data.buildings[building].effects.trade_fee_modifier
            for city in state.cities
            if city.owner == player
            for building in city.buildings
        ),
        default=0.0,
    )
    return max(fee * (1 + Decimal(str(min(best, 0.0)))), Decimal(0))


def with_fee(state: CivState, data: CivData, player: str, amounts: Mapping[Resource, int]):
    """What handing these amounts over costs the nation, its fee included (rounded down)."""
    fee = trade_fee(state, data, player)
    return {r: amount + int(amount * fee) for r, amount in amounts.items()}


# --- orders -----------------------------------------------------------------
# A `*_problem` function returns None when the order is legal, otherwise a
# message that tells the player how to fix it. The order itself must be legal.


def message_problem(state: CivState, sender: str, text: str, to: str | None) -> str | None:
    if to is not None and (problem := _other_nation(state, sender, to)):
        return problem
    if not text.strip():
        return "The message is empty."
    if len(text) > MESSAGE_CHARS:
        return f"The message has {len(text)} characters; at most {MESSAGE_CHARS} are sent."
    return None


def message(state: CivState, ctx: TurnContext, sender: str, text: str, to: str | None = None):
    """Say something to every nation, or with `to` to that nation alone."""
    must_be_legal(message_problem(state, sender, text, to))
    ctx.emit(
        MESSAGE, {"player": sender, "text": text}, visible_to=None if to is None else [sender, to]
    )


def treaty_problem(
    state: CivState,
    data: CivData,
    sender: str,
    to: str,
    treaty: str,
    rounds: int | None = None,
    payer: str | None = None,
    payment: Mapping[Resource, int] | None = None,
) -> str | None:
    """Whether `sender` may offer `to` this treaty now; also checked again when it is accepted."""
    if problem := _other_nation(state, sender, to):
        return problem
    kind = data.treaties.get(treaty)
    if kind is None:
        return f"There is no treaty '{treaty}'. Treaties: {', '.join(data.treaties)}."
    if kind.duration_rounds is None and rounds is not None:
        return f"A {kind.name} lasts until it is broken; leave out the rounds."
    if kind.duration_rounds is not None and rounds is not None:
        low, high = kind.duration_rounds.min, kind.duration_rounds.max
        if not low <= rounds <= high:
            return f"A {kind.name} lasts {low} to {high} rounds, not {rounds}."
    if kind.payment_per_round:
        if payer not in (sender, to):
            return f"Say who pays the {kind.name}: {sender} or {to}."
        if problem := _amounts_problem(payment or {}, "payment per round"):
            return problem
    elif payer is not None or payment:
        return f"A {kind.name} has no payment; leave out payer and payment."
    if any(pact.kind == treaty for pact in treaties_between(state, sender, to)):
        return f"You already have a {kind.name} with {to}."
    if treaty != "peace" and at_war(state, sender, to):
        return f"You are at war with {to}: offer peace first."
    return None


def propose_treaty(
    state: CivState,
    data: CivData,
    ctx: TurnContext,
    sender: str,
    to: str,
    treaty: str,
    rounds: int | None = None,
    payer: str | None = None,
    payment: Mapping[Resource, int] | None = None,
) -> str:
    """Offer a treaty; it is signed if `to` accepts it this round. Returns the offer id."""
    must_be_legal(treaty_problem(state, data, sender, to, treaty, rounds, payer, payment))
    duration = data.treaties[treaty].duration_rounds
    offer = f"o{state.offers_made + 1}"
    ctx.emit(
        "treaty_offered",
        {
            "offer": offer,
            "sender": sender,
            "to": to,
            "round": state.round,
            "treaty": treaty,
            "rounds": rounds if duration is None or rounds is not None else duration.default,
            "payer": payer,
            "payment": dict(payment or {}),
        },
        visible_to=[sender, to],
    )
    return offer


def trade_problem(
    state: CivState,
    data: CivData,
    sender: str,
    to: str,
    gives: Mapping[Resource, int],
    wants: Mapping[Resource, int],
    rounds: int = 1,
) -> str | None:
    if problem := _other_nation(state, sender, to):
        return problem
    if not gives and not wants:
        return "A trade needs something to give or to get."
    if problem := _amounts_problem(gives, "what you give") or _amounts_problem(
        wants, "what you want"
    ):
        return problem
    longest = data.balance.trade.max_rounds
    if not 1 <= rounds <= longest:
        return f"A trade runs 1 to {longest} rounds, not {rounds}."
    if at_war(state, sender, to):
        return f"You are at war with {to}: no trade until there is peace."
    return _cannot_pay(state, data, sender, gives)


def propose_trade(
    state: CivState,
    data: CivData,
    ctx: TurnContext,
    sender: str,
    to: str,
    gives: Mapping[Resource, int],
    wants: Mapping[Resource, int],
    rounds: int = 1,
) -> str:
    """Offer `gives` for `wants`, every round for `rounds` rounds. Returns the offer id."""
    must_be_legal(trade_problem(state, data, sender, to, gives, wants, rounds))
    offer = f"o{state.offers_made + 1}"
    ctx.emit(
        "trade_offered",
        {
            "offer": offer,
            "sender": sender,
            "to": to,
            "round": state.round,
            "gives": dict(gives),
            "wants": dict(wants),
            "rounds": rounds,
        },
        visible_to=[sender, to],
    )
    return offer


def answer_problem(
    state: CivState, data: CivData, player: str, offer_id: str, accept: bool, kind: str
) -> str | None:
    """Whether `player` may answer this offer; accepting checks the offer again as it is now."""
    open_ = [o for o in state.offers if o.to == player and (o.treaty is None) == (kind == "trade")]
    offer = next((o for o in open_ if o.id == offer_id), None)
    if offer is None:
        ids = ", ".join(o.id for o in open_) or "none"
        return f"There is no open {kind} offer '{offer_id}' to you. Open {kind} offers: {ids}."
    if not accept:
        return None
    if offer.treaty is not None:
        problem = treaty_problem(
            state, data, offer.sender, offer.to, offer.treaty, None, offer.payer, offer.payment
        )
        return None if problem is None else f"The offer cannot be signed now: {problem}"
    problem = trade_problem(
        state, data, offer.sender, offer.to, offer.gives, offer.wants, offer.rounds or 1
    )
    if problem is None:
        problem = _cannot_pay(state, data, offer.to, offer.wants)
    return None if problem is None else f"The trade cannot be agreed now: {problem}"


def respond_treaty(
    state: CivState, data: CivData, ctx: TurnContext, player: str, offer_id: str, accept: bool
) -> str | None:
    """Accept or decline a treaty offer. Returns the id of the signed treaty, if any."""
    must_be_legal(answer_problem(state, data, player, offer_id, accept, "treaty"))
    offer = next(o for o in state.offers if o.id == offer_id)
    if not accept:
        ctx.emit("treaty_declined", {"offer": offer_id}, visible_to=[offer.sender, offer.to])
        return None
    treaty = f"t{state.treaties_signed + 1}"
    ctx.emit(
        "treaty_signed",
        {
            "treaty": treaty,
            "offer": offer_id,
            "kind": offer.treaty,
            "parties": pair(offer.sender, offer.to),
            # A treaty for 10 rounds holds in this round and the next nine.
            "ends_round": None if offer.rounds is None else state.round + offer.rounds - 1,
            "payer": offer.payer,
            "payment": dict(offer.payment),
            "ends_war": at_war(state, offer.sender, offer.to),
        },
    )
    return treaty


def respond_trade(
    state: CivState, data: CivData, ctx: TurnContext, player: str, offer_id: str, accept: bool
) -> None:
    """Accept or decline a trade offer. An accepted trade is carried out in the trade step."""
    must_be_legal(answer_problem(state, data, player, offer_id, accept, "trade"))
    offer = next(o for o in state.offers if o.id == offer_id)
    if not accept:
        ctx.emit("trade_declined", {"offer": offer_id}, visible_to=[offer.sender, offer.to])
        return
    ctx.emit("trade_agreed", {"offer": offer_id}, visible_to=[offer.sender, offer.to])


def break_problem(state: CivState, player: str, treaty_id: str) -> str | None:
    own = [pact.id for pact in state.treaties if player in pact.parties]
    if treaty_id in own:
        return None
    return f"You have no treaty '{treaty_id}'. Your treaties: {', '.join(own) or 'none'}."


def break_treaty(
    state: CivState, data: CivData, ctx: TurnContext, player: str, treaty_id: str
) -> None:
    """End a treaty before its time. Everyone sees it, and it costs the breaker reputation."""
    must_be_legal(break_problem(state, player, treaty_id))
    ctx.emit(
        "treaty_broken",
        {
            "treaty": treaty_id,
            "by": player,
            "reputation": _reputation_after(state, data, player, 1),
        },
    )


def war_problem(state: CivState, player: str, on: str) -> str | None:
    if problem := _other_nation(state, player, on):
        return problem
    if at_war(state, player, on):
        return f"You are already at war with {on}."
    return None


def declare_war(state: CivState, data: CivData, ctx: TurnContext, player: str, on: str) -> None:
    """Go to war. Every treaty between the two ends, each a broken one for the declarer.

    The allies of the nation attacked join the war against the declarer, except
    those bound by a treaty with it that forbids an attack: an alliance does not
    make them break their word.
    """
    must_be_legal(war_problem(state, player, on))
    broken = [pact.id for pact in treaties_between(state, player, on)]
    joined = [
        ally
        for ally in allies(state, data, on)
        if ally != player
        and not at_war(state, ally, player)
        and may_attack(state, data, ally, player) is None
    ]
    ctx.emit(
        "war_declared",
        {
            "by": player,
            "on": on,
            "broken": broken,
            "joined": joined,
            "reputation": _reputation_after(state, data, player, len(broken)),
        },
    )


# --- the steps of a round ---------------------------------------------------


def expire(state: CivState, ctx: TurnContext) -> None:
    """At the start of a round: unanswered offers lapse, ended treaties go.

    A nation acts once a round, so an offer made in round r is answered in round r + 1
    and lapses when round r + 2 starts (docs/civ-interfaces.md).
    """
    for offer in list(state.offers):
        if offer.round < state.round - 1:
            ctx.emit("offer_lapsed", {"offer": offer.id}, visible_to=[offer.sender, offer.to])
    for pact in list(state.treaties):
        if pact.ends_round is not None and pact.ends_round < state.round:
            ctx.emit("treaty_expired", {"treaty": pact.id})


def settle(state: CivState, data: CivData, ctx: TurnContext) -> None:
    """The trade step: tributes are paid, then agreed trades are carried out, oldest first.

    A tribute pays what the payer's stock holds of it, up to the amount. A trade
    is carried out whole or not at all: if either side cannot pay its part and
    its fee, the trade fails and ends.
    """
    for pact in state.treaties:
        if pact.payer is None:
            continue
        (payee,) = (p for p in pact.parties if p != pact.payer)
        stock = state.nations[pact.payer].stock
        paid = {r: min(amount, stock[r]) for r, amount in pact.payment.items()}
        ctx.emit(
            "tribute_paid",
            {"treaty": pact.id, "payer": pact.payer, "payee": payee, "paid": paid},
            visible_to=[pact.payer, payee],
        )
    for deal in list(state.deals):
        short = [
            player
            for player, amounts in ((deal.sender, deal.gives), (deal.to, deal.wants))
            if _cannot_pay(state, data, player, amounts)
        ]
        if short:
            ctx.emit(
                "trade_failed", {"deal": deal.id, "short": short}, visible_to=[deal.sender, deal.to]
            )
            continue
        ctx.emit(
            "trade_done",
            {
                "deal": deal.id,
                "paid": {
                    deal.sender: with_fee(state, data, deal.sender, deal.gives),
                    deal.to: with_fee(state, data, deal.to, deal.wants),
                },
                "received": {deal.sender: dict(deal.wants), deal.to: dict(deal.gives)},
                "rounds_left": deal.rounds_left - 1,
            },
            visible_to=[deal.sender, deal.to],
        )


# --- helpers ----------------------------------------------------------------


def _other_nation(state: CivState, player: str, other: str) -> str | None:
    if other in state.nations and other != player:
        return None
    others = ", ".join(n for n in state.nations if n != player)
    return f"'{other}' is not another nation. The others: {others}."


def _amounts_problem(amounts: Mapping[str, Any], what: str) -> str | None:
    for resource, amount in amounts.items():
        if resource not in RESOURCES:
            return f"In {what}: '{resource}' is not a resource. Resources: {', '.join(RESOURCES)}."
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 1:
            return f"In {what}: {resource} must be a whole number of at least 1, not {amount!r}."
    if not amounts and what == "payment per round":
        return 'A tribute needs a payment per round, such as {"gold": 5}.'
    return None


def _cannot_pay(state: CivState, data: CivData, player: str, amounts: Mapping[Resource, int]):
    due = with_fee(state, data, player, amounts)
    stock = state.nations[player].stock
    if all(stock[r] >= amount for r, amount in due.items()):
        return None
    text = ", ".join(f"{due[r]} {r}" for r in RESOURCES if r in due)
    have = ", ".join(f"{stock[r]} {r}" for r in RESOURCES if r in due)
    return f"{player} needs {text} with the trade fee and has {have}."


def _reputation_after(state: CivState, data: CivData, player: str, broken: int) -> int:
    rules = data.reputation
    value = state.nations[player].reputation + rules.break_treaty_penalty * broken
    return max(rules.min, min(rules.max, value))


# --- events -----------------------------------------------------------------
# Events carry outcomes: applying one needs no game data.


def _message(state: CivState, data: dict[str, Any]) -> None:
    pass  # words change nothing in the state; the log keeps them


def _offered(state: CivState, data: dict[str, Any]) -> None:
    fields = {k: data[k] for k in ("sender", "to", "round", "rounds")}
    if "treaty" in data:
        offer = Offer(
            id=data["offer"],
            treaty=data["treaty"],
            payer=data["payer"],
            payment=data["payment"],
            **fields,
        )
    else:
        offer = Offer(id=data["offer"], gives=data["gives"], wants=data["wants"], **fields)
    state.offers.append(offer)
    state.offers_made += 1


def _offer_closed(state: CivState, data: dict[str, Any]) -> None:
    state.offers = [offer for offer in state.offers if offer.id != data["offer"]]


def _treaty_signed(state: CivState, data: dict[str, Any]) -> None:
    _offer_closed(state, data)
    state.treaties.append(
        Pact(
            id=data["treaty"],
            kind=data["kind"],
            parties=data["parties"],
            ends_round=data["ends_round"],
            payer=data["payer"],
            payment=data["payment"],
        )
    )
    state.treaties_signed += 1
    if data["ends_war"]:
        state.wars.remove(data["parties"])


def _trade_agreed(state: CivState, data: dict[str, Any]) -> None:
    offer = next(o for o in state.offers if o.id == data["offer"])
    _offer_closed(state, data)
    state.deals.append(
        Deal(
            id=offer.id,
            sender=offer.sender,
            to=offer.to,
            gives=offer.gives,
            wants=offer.wants,
            rounds_left=offer.rounds or 1,
        )
    )


def _treaty_ended(state: CivState, data: dict[str, Any]) -> None:
    state.treaties = [pact for pact in state.treaties if pact.id != data["treaty"]]


def _treaty_broken(state: CivState, data: dict[str, Any]) -> None:
    _treaty_ended(state, data)
    state.nations[data["by"]].reputation = data["reputation"]


def _war_declared(state: CivState, data: dict[str, Any]) -> None:
    state.treaties = [pact for pact in state.treaties if pact.id not in data["broken"]]
    state.nations[data["by"]].reputation = data["reputation"]
    for enemy in [data["on"], *data["joined"]]:
        state.wars.append(pair(data["by"], enemy))
    # Trades between enemies stop with the war.
    enemies = {tuple(war) for war in state.wars}
    state.deals = [d for d in state.deals if tuple(pair(d.sender, d.to)) not in enemies]


def _tribute_paid(state: CivState, data: dict[str, Any]) -> None:
    for resource, amount in data["paid"].items():
        state.nations[data["payer"]].stock[resource] -= amount
        state.nations[data["payee"]].stock[resource] += amount


def _trade_failed(state: CivState, data: dict[str, Any]) -> None:
    state.deals = [deal for deal in state.deals if deal.id != data["deal"]]


def _trade_done(state: CivState, data: dict[str, Any]) -> None:
    for player, amounts in data["paid"].items():
        for resource, amount in amounts.items():
            state.nations[player].stock[resource] -= amount
    for player, amounts in data["received"].items():
        for resource, amount in amounts.items():
            state.nations[player].stock[resource] += amount
    deal = next(deal for deal in state.deals if deal.id == data["deal"])
    deal.rounds_left = data["rounds_left"]
    if deal.rounds_left == 0:
        state.deals.remove(deal)


APPLIERS: dict[str, Callable[[CivState, dict[str, Any]], None]] = {
    MESSAGE: _message,
    "treaty_offered": _offered,
    "trade_offered": _offered,
    "treaty_declined": _offer_closed,
    "trade_declined": _offer_closed,
    "offer_lapsed": _offer_closed,
    "treaty_signed": _treaty_signed,
    "trade_agreed": _trade_agreed,
    "treaty_expired": _treaty_ended,
    "treaty_broken": _treaty_broken,
    "war_declared": _war_declared,
    "tribute_paid": _tribute_paid,
    "trade_failed": _trade_failed,
    "trade_done": _trade_done,
}
