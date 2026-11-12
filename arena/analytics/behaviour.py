# ruff: noqa: E501  (lines of prose)
"""How each player behaves: descriptive style tags with their evidence, for the behaviour cards.

Rules (the Researcher's, docs/METRICS.md "Behaviour"):

- No tag below MIN_N own decisions of the kind it describes, and never from
  fallback moves. Below that a player is "too early to tell (n of 10)".
- A rate tag needs its whole Wilson 95 % interval on the right side of the
  threshold: the lower end above it ("Bluffer"), or the upper end below it
  ("Honest"). 7 lies in 10 plays is not yet a bluffer; 25 in 35 is.
- Tags that need hidden cards (Bluffer, Honest, Sharp eye, Risk-taker) or
  private events (Rule-breaker: refused answers; Often replaced by the bot)
  appear only with spoilers. Speed tags compare with the other seats of the match and
  read "slow/quick to answer": response time includes the network.

Pure functions of the analytics of one match; every threshold is a constant here.
"""

import math
from statistics import median
from typing import Any

MIN_N = 10  # own decisions of a kind before any tag about it
Z = 1.96  # Wilson 95 % interval

BLUFFER_ABOVE = 0.5  # chosen-lie rate: lies when an honest play was possible
HONEST_BELOW = 0.15
CAUTIOUS_BELOW = 0.15  # call rate of call opportunities
TRIGGER_HAPPY_ABOVE = 0.5
SHARP_EYE_GAP = 0.2  # hit rate at least this far above the false-alarm rate
RISK_TAKER_RISK = 0.33  # a lie at this revolver risk or more is a risky lie
RISK_TAKER_TIMES = 3
RISK_TAKER_SHARE = 0.5  # and those risky lies are at least half of the plays at that risk
RULE_BREAKER_ABOVE = 0.25  # rejected answers per own move
REPLACED_ABOVE = 0.10  # share of moves the random bot played instead
CUT_OFF_ABOVE = 0.10  # answers cut off at the output limit, per move
THROTTLED_ABOVE = 0.20  # calls refused as too many requests, per move
SLOW_FACTOR = 2.0  # median response time against the other seats' median
QUICK_FACTOR = 0.5

LABELS = {
    "bluffer": ("Bluffer", "Bluffer"),
    "honest": ("Honest", "Ehrlich"),
    "cautious": ("Cautious", "Vorsichtig"),
    "trigger_happy": ("Trigger-happy", "Schnell beim Rufen"),
    "sharp_eye": ("Sharp eye", "Scharfes Auge"),
    "risk_taker": ("Risk-taker", "Risikofreudig"),
    "rule_breaker": ("Rule-breaker", "Regelbrecher"),
    "replaced": ("Often replaced by the bot", "Oft vom Bot ersetzt"),
    "cut_off": ("Answers cut off", "Antworten abgeschnitten"),
    "throttled": ("Often rate-limited", "Oft gedrosselt"),
    "slow": ("Slow to answer", "Antwortet langsam"),
    "quick": ("Quick to answer", "Antwortet schnell"),
}


def wilson(part: int, whole: int) -> tuple[float, float] | None:
    """The Wilson 95 % interval of part / whole; None without any case."""
    if whole == 0:
        return None
    p = part / whole
    centre = p + Z * Z / (2 * whole)
    spread = Z * math.sqrt(p * (1 - p) / whole + Z * Z / (4 * whole * whole))
    low, high = (centre - spread) / (1 + Z * Z / whole), (centre + spread) / (1 + Z * Z / whole)
    return max(low, 0.0), min(high, 1.0)


def _percent(value: float) -> str:
    return f"{round(value * 100)} %"


def _rate_tag(
    tag: str,
    rate: dict | None,
    above: float | None,
    below: float | None,
    spoilers_only: bool,
    what: tuple[str, str],
):
    """A tag from a rate if n is enough and the interval clears the threshold; else None."""
    if not rate or rate["of"] < MIN_N:
        return None
    low, high = wilson(rate["n"], rate["of"])
    if (above is not None and low > above) or (below is not None and high < below):
        en, de = what  # templates with {p}, the rate as a percent
        interval = f"95 %: {round(low * 100)}-{_percent(high)}, n={rate['of']}"
        return _tag(
            tag,
            "style",
            spoilers_only,
            rate["value"],
            rate["n"],
            rate["of"],
            en.format(p=_percent(rate["value"])) + f" ({interval})",
            de.format(p=_percent(rate["value"])) + f" ({interval})",
            [low, high],
        )
    return None


def _tag(tag, kind, spoilers_only, value, n, of, en, de, interval=None):
    label_en, label_de = LABELS[tag]
    return {
        "id": tag,
        "kind": kind,  # "style" or "reliability"
        "spoilers": spoilers_only,
        "label": {"en": label_en, "de": label_de},
        "text": {"en": en, "de": de},
        "value": value,
        "n": n,
        "of": of,
        "interval": interval,
    }


THOUGHT_CHARS = 200  # the last thought is cut to this length for the card


def liars_deck(
    analytics: dict[str, Any], spoilers: bool, thoughts: dict[str, str]
) -> dict[str, Any]:
    """The behaviour of every player of a Liar's Deck match, from its analytics.

    `thoughts`: each player's last thought, read from the log (spectator view only).
    """
    moves = analytics["moves"]
    own = {
        p: [m for m in moves if m["player"] == p and not m["fallback"] and not m.get("automatic")]
        for p in analytics["players"]
    }
    latency = {p: [m["latency_ms"] for m in own[p] if m["latency_ms"] is not None] for p in own}
    result = {}
    for player in analytics["players"]:
        totals = analytics["totals"][player]
        mine = own[player]
        tags = []
        if spoilers:
            tags.append(
                _rate_tag(
                    "bluffer",
                    totals["chosen_lie_rate"],
                    BLUFFER_ABOVE,
                    None,
                    True,
                    (
                        "lies in {p} of plays with an honest card in hand",
                        "lügt in {p} der Züge mit einer ehrlichen Karte auf der Hand",
                    ),
                )
            )
            tags.append(
                _rate_tag(
                    "honest",
                    totals["chosen_lie_rate"],
                    None,
                    HONEST_BELOW,
                    True,
                    (
                        "lies in only {p} of plays with an honest card in hand",
                        "lügt nur in {p} der Züge mit einer ehrlichen Karte auf der Hand",
                    ),
                )
            )
            tags.append(_sharp_eye(totals))
            tags.append(_risk_taker(mine))
            # Refused answers and bot moves are private events: judged in the spectator view.
            tags.append(_rule_breaker(mine))
            tags.append(_replaced(totals))
            tags.append(_cut_off(totals))
            tags.append(_throttled(totals))
        tags.append(
            _rate_tag(
                "cautious",
                totals["call_rate"],
                None,
                CAUTIOUS_BELOW,
                False,
                (
                    "calls a liar at only {p} of chances",
                    "ruft nur bei {p} der Gelegenheiten Lügner",
                ),
            )
        )
        tags.append(
            _rate_tag(
                "trigger_happy",
                totals["call_rate"],
                TRIGGER_HAPPY_ABOVE,
                None,
                False,
                ("calls a liar at {p} of chances", "ruft bei {p} der Gelegenheiten Lügner"),
            )
        )
        tags.append(_speed(player, latency))
        tags = [tag for tag in tags if tag is not None]
        result[player] = {
            "tags": tags,
            "too_early": None if len(mine) >= MIN_N else {"n": len(mine), "need": MIN_N},
            "compare": _compare(player, analytics, spoilers),
        }
        if spoilers:  # a spoiler-free answer does not even name the field
            result[player]["last_thought"] = _cut(thoughts.get(player))
    return result


def _sharp_eye(totals: dict) -> dict | None:
    hit, alarm = totals["hit_rate"], totals["false_alarm_rate"]
    if not hit or not alarm or hit["of"] < MIN_N or alarm["of"] < MIN_N:
        return None
    gap = hit["value"] - alarm["value"]
    (hit_low, _), (_, alarm_high) = wilson(hit["n"], hit["of"]), wilson(alarm["n"], alarm["of"])
    if gap < SHARP_EYE_GAP or hit_low <= alarm_high:
        return None
    return _tag(
        "sharp_eye",
        "style",
        True,
        gap,
        hit["n"],
        hit["of"],
        f"calls {_percent(hit['value'])} of lies but only {_percent(alarm['value'])} of honest plays (n={hit['of']} and {alarm['of']})",
        f"ruft bei {_percent(hit['value'])} der Lügen, aber nur bei {_percent(alarm['value'])} der ehrlichen Karten (n={hit['of']} und {alarm['of']})",
    )


def _risk_taker(mine: list[dict]) -> dict | None:
    """Lies at a high revolver risk: at least 3 of them, and at least half of such plays."""
    plays = [m for m in mine if m["kind"] == "play"]
    if len(plays) < MIN_N:
        return None
    exposed = [m for m in plays if m["honest"] is not None and (m["risk"] or 0) >= RISK_TAKER_RISK]
    risky = sum(1 for m in exposed if m["honest"] is False)
    if risky < RISK_TAKER_TIMES or risky < RISK_TAKER_SHARE * len(exposed):
        return None
    share = _percent(RISK_TAKER_RISK)
    return _tag(
        "risk_taker",
        "style",
        True,
        risky / len(exposed),
        risky,
        len(exposed),
        f"lied {risky} of the {len(exposed)} times it played at a {share} or higher chance that the next pull fires",
        f"log {risky} von {len(exposed)} Mal, als es bei {share} oder mehr Gefahr spielte, dass der nächste Abzug losgeht",
    )


def _rule_breaker(mine: list[dict]) -> dict | None:
    if len(mine) < MIN_N:
        return None
    per_move = sum(m["rejected"] for m in mine) / len(mine)
    if per_move <= RULE_BREAKER_ABOVE:
        return None
    return _tag(
        "rule_breaker",
        "style",
        True,
        per_move,
        sum(m["rejected"] for m in mine),
        len(mine),
        f"{per_move:.2f} refused answers per move (n={len(mine)})",
        f"{per_move:.2f} abgelehnte Antworten pro Zug (n={len(mine)})",
    )


def _replaced(totals: dict) -> dict | None:
    share = totals["fallback_share"]
    if share["of"] < MIN_N or share["value"] <= REPLACED_ABOVE:
        return None
    return _tag(
        "replaced",
        "reliability",
        True,
        share["value"],
        share["n"],
        share["of"],
        f"the random bot played {share['n']} of {share['of']} moves",
        f"der Zufallsbot spielte {share['n']} von {share['of']} Zügen",
    )


def _per_move(totals: dict, field: str, above: float) -> float | None:
    moves = totals.get("moves") or 0
    value = totals.get(field) or 0
    return value / moves if moves >= MIN_N and value / moves > above else None


def _cut_off(totals: dict) -> dict | None:
    """Answers that ran into the output limit: a setting to raise, not a missing skill."""
    rate = _per_move(totals, "cutoffs", CUT_OFF_ABOVE)
    if rate is None:
        return None
    n, of = totals["cutoffs"], totals["moves"]
    return _tag(
        "cut_off",
        "reliability",
        True,
        rate,
        n,
        of,
        f"{n} answers in {of} moves ran into the output limit (a setting, not missing tools)",
        f"{n} Antworten in {of} Zügen liefen ins Ausgabelimit (eine Einstellung, keine fehlenden Tools)",
    )


def _throttled(totals: dict) -> dict | None:
    """Calls the provider refused as too many requests: the route, not the model."""
    rate = _per_move(totals, "rate_limits", THROTTLED_ABOVE)
    if rate is None:
        return None
    n, of = totals["rate_limits"], totals["moves"]
    return _tag(
        "throttled",
        "reliability",
        True,
        rate,
        n,
        of,
        f"{n} calls in {of} moves were refused as too many requests (the provider route)",
        f"{n} Aufrufe in {of} Zügen wurden als zu viele Anfragen abgelehnt (der Anbieterweg)",
    )


def _speed(player: str, latency: dict[str, list[int]]) -> dict | None:
    mine = latency[player]
    others = [ms for p, times in latency.items() if p != player for ms in times]
    if len(mine) < MIN_N or len(others) < MIN_N:
        return None
    ratio = median(mine) / median(others) if median(others) else None
    if ratio is None or QUICK_FACTOR <= ratio <= SLOW_FACTOR:
        return None
    seconds = median(mine) / 1000
    tag = "slow" if ratio > SLOW_FACTOR else "quick"
    return _tag(
        tag,
        "style",
        False,
        ratio,
        len(mine),
        len(mine),
        f"answers in {seconds:.1f} s (median), {ratio:.1f}× the other seats; includes the network",
        f"antwortet in {seconds:.1f} s (Median), {ratio:.1f}× die anderen Plätze; inklusive Netzwerk",
    )


def _compare(player: str, analytics: dict, spoilers: bool) -> dict[str, str]:
    """Each rate against the other seats pooled: "above", "below", "about" or "too few"."""
    names = ["call_rate", "call_accuracy"] + (["chosen_lie_rate"] if spoilers else [])
    verdicts = {}
    for name in names:
        mine = analytics["totals"][player][name]
        others = [analytics["totals"][p][name] for p in analytics["players"] if p != player]
        n, of = sum(o["n"] for o in others if o), sum(o["of"] for o in others if o)
        if not mine or mine["of"] < MIN_N or of < MIN_N:
            verdicts[name] = "too few"
            continue
        (low, high), (o_low, o_high) = wilson(mine["n"], mine["of"]), wilson(n, of)
        verdicts[name] = "above" if low > o_high else "below" if high < o_low else "about"
    return verdicts


def _cut(text: str | None) -> str | None:
    if text is None or len(text) <= THOUGHT_CHARS:
        return text
    return text[: THOUGHT_CHARS - 1].rstrip() + "…"
