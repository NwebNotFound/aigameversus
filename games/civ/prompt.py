"""What a model reads about Throne of Tokens: rules per prompt version, and the situation summary.

Three factors, each a match setting, each recorded in `match_started`, each off or baseline by
default so a match that sets none of them reads `rules.md` as it is (docs/decisions, the scheme
of the prompt proposal):

- `prompt_version`: `civ-p1` (the baseline: `rules.md` and the observation) or `civ-p2` (the same
  rules plus a short summary above the situation, worked out from the observation only: the
  standing in each way to win, what can be done now, what was refused, who is near).
- `strategy_text`: `off` or `v1`, one neutral paragraph about playing for the whole match, the
  same words for every model.
- `private_plan`: `off` or `on`, whether `submit_orders` takes a `plan` that comes back to the
  nation next round (the plugin removes the field when it is off).

All functions are pure.
"""

from collections.abc import Mapping
from importlib import resources
from typing import Any

from games.civ.world import distance

VERSIONS = ("civ-p1", "civ-p2")
DEFAULT_VERSION = "civ-p1"
STRATEGY_TEXTS = ("off", "v1")
PLAN_SETTINGS = ("off", "on")
SETTINGS = ("prompt_version", "strategy_text", "private_plan")

SUMMARY_GUIDE = """
## Your summary

Above your situation you get a short summary of it: how far you are from each way to win, what
you can do now, which of your orders were refused last round, and which foreign armies stand
near your cities. It says nothing that your situation does not.
"""

STRATEGY_V1 = """
## Think about the whole match

- Aim to win the whole match, not the next round. Deceiving and breaking promises are allowed in
  this game; keeping a treaty and breaking it are both choices.
- Name the way to win you are playing for, and compare the legal options for this round by what
  the other nations will probably do next and what you will do in the round after.
- Weigh economy against army this round: what you spend on one you cannot spend on the other.
- Other nations choose what they tell you, so a promise or a calm message is weak evidence. Trust
  what your own map, your own cities and the public scoreboard show.
- Give a short reason in `thought`, then submit your orders.
"""

PLAN_ON = """
## Your plan

`plan` (optional, at most 60 words) in `submit_orders` is a note to yourself. You get it back next
round as `your_plan_from_last_round`; nobody else reads it. Write what you are working towards
and what you will do next.

```json
{"orders": [], "plan": "Grow c1, settle east, keep a1 near the river."}
```
"""


def _choice(settings: Mapping[str, Any] | None, key: str, allowed: tuple[str, ...], default: str):
    value = (settings or {}).get(key, default)
    if value not in allowed:
        raise ValueError(f"Unknown {key} {value!r}; choose one of {list(allowed)}")
    return value


def version_of(settings: Mapping[str, Any] | None) -> str:
    """The prompt version of a match: its `prompt_version` setting, else the baseline."""
    return _choice(settings, "prompt_version", VERSIONS, DEFAULT_VERSION)


def strategy_of(settings: Mapping[str, Any] | None) -> str:
    return _choice(settings, "strategy_text", STRATEGY_TEXTS, "off")


def plan_of(settings: Mapping[str, Any] | None) -> str:
    return _choice(settings, "private_plan", PLAN_SETTINGS, "off")


def check(settings: Mapping[str, Any] | None) -> None:
    """Refuse a setting with a value the prompt does not know."""
    version_of(settings)
    strategy_of(settings)
    plan_of(settings)


def base_rules() -> str:
    return resources.files("games.civ").joinpath("rules.md").read_text(encoding="utf-8")


def rules_text(settings: Mapping[str, Any] | None = None) -> str:
    """`rules.md` and what the settings add to it; with none set, `rules.md` itself."""
    text = base_rules()
    if version_of(settings) == "civ-p2":
        text += SUMMARY_GUIDE
    if plan_of(settings) == "on":
        text += PLAN_ON
    if strategy_of(settings) == "v1":
        text += STRATEGY_V1
    return text


def _words(amounts: Mapping[str, int]) -> str:
    return ", ".join(f"{n} {resource}" for resource, n in amounts.items() if n) or "nothing"


def situation_summary(observation: Mapping[str, Any]) -> str:
    """Your round at a glance (version civ-p2), from the observation alone."""
    you, victory = observation["you"], observation["victory"]
    lines = [
        f"You are {you}. Round {observation['round']} of {observation['rounds_total']}.",
        f"Domination: {victory['domination']}. Economy: {victory['economy']}.",
        f"Score: {victory['score']}. Closest way to win: {victory['closest_win']}.",
        f"Stock: {_words(observation['stock'])}. Income per round: "
        f"{_words(observation['income_per_round'])}.",
    ]
    if observation["unpaid_rounds"]:
        lines.append(f"Upkeep went unpaid for {observation['unpaid_rounds']} round(s) in a row.")
    options = []
    for city in observation["cities"]:
        legal = observation["legal"]["cities"].get(city["id"], {})
        build, train = sorted(legal.get("build", {})), legal.get("train", {})
        options.append(
            f"{city['id']}: build {', '.join(build) or 'nothing'}; train "
            f"{', '.join(f'{u} up to {n}' for u, n in train.items()) or 'nothing'}"
            f" ({city['slots_free']} slot(s) free)"
        )
    lines.append("You can now: " + " | ".join(options) if options else "You have no cities.")
    moving = [
        f"{a['id']} ({len(a['reachable'])} tiles{', can settle' if a['can_settle'] else ''})"
        for a in observation["armies"]
        if a["reachable"] or a["can_settle"]
    ]
    if moving:
        lines.append("Armies that can act: " + ", ".join(moving) + ".")
    if observation["refused"]:
        shown = [f"{r.get('order')}: {r.get('reason')}" for r in observation["refused"][:5]]
        lines.append("Refused last round: " + "; ".join(shown) + ".")
    if observation["offers"]:
        lines.append(
            "Offers waiting for your answer: "
            + ", ".join(f"{o['id']} from {o['from']}" for o in observation["offers"])
            + "."
        )
    near = _near(observation)
    if near:
        lines.append("Foreign armies near your cities: " + "; ".join(near) + ".")
    return "\n".join(lines)


def _near(observation: Mapping[str, Any], within: int = 3) -> list[str]:
    """Foreign armies in sight within `within` tiles of one of your cities."""
    found = []
    for army in observation["seen"]["armies"]:
        spot = tuple(army["tile"])
        close = [
            (distance(tuple(c["tile"]), spot), c["id"])
            for c in observation["cities"]
            if distance(tuple(c["tile"]), spot) <= within
        ]
        if close:
            steps, city = min(close)
            found.append(
                f"{army['owner']}'s {army['id']} ({army['units']} unit(s)) "
                f"{steps} step(s) from {city}"
            )
    return found
