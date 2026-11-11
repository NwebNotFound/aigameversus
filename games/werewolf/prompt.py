# ruff: noqa: E501  (lines of prose)
"""What a model reads about Werewolf: rules per prompt version and the situation summary.

- `werewolf-p1`: `rules.md` as it was, no summary.
- `werewolf-p2`: `rules_v2.md` and a short summary above the situation, worked out from the
  observation only: your role and what you win with, the phase, who lives, the pack, the votes,
  and your own secrets (seer results, potions, lovers). It states nothing the player does not see.

All functions are pure.
"""

from collections.abc import Mapping
from importlib import resources
from typing import Any

VERSIONS = ("werewolf-p1", "werewolf-p2")
DEFAULT_VERSION = "werewolf-p1"
_FILES = {"werewolf-p1": "rules.md", "werewolf-p2": "rules_v2.md"}

GOALS = {
    "village": "You win when every werewolf is dead. Find the wolves; do not waste your vote on villagers.",
    "wolves": "You win when wolves are at least as many as everyone else alive. Kill at night, blend in by day.",
    "solo": "You play alone and win only as the last player alive.",
}


def version_of(settings: Mapping[str, Any] | None) -> str:
    """The prompt version of a match: its `prompt_version` setting, else the default."""
    version = (settings or {}).get("prompt_version", DEFAULT_VERSION)
    if version not in VERSIONS:
        raise ValueError(f"Unknown prompt_version {version!r}; choose one of {list(VERSIONS)}")
    return version


def rules_text(version: str) -> str:
    return resources.files("games.werewolf").joinpath(_FILES[version]).read_text(encoding="utf-8")


def _names(players: list[str]) -> str:
    return ", ".join(players) if players else "nobody"


def situation_summary(observation: Mapping[str, Any]) -> str:
    """Your turn at a glance, for the top of the prompt (version p2)."""
    you = observation["you"]
    role = observation["role"]
    alive = observation["alive"]
    others = [p for p in alive if p != you]
    phase = observation["phase"]
    when = f"night {observation['night']}" if phase == "night" else f"day {observation['day']}"

    lines = []
    if role:
        lines.append(
            f"You are {you}, the {role['name']} ({role['id']}), team {role['team']}. {GOALS.get(role['team'], '')}".rstrip()
        )
    lines.append(f"It is {when} ({phase}). {len(alive)} alive: {_names(alive)}.")
    if observation["dead"]:
        lines.append(
            "Dead: "
            + "; ".join(f"{d['player']} was {d['role']}" for d in observation["dead"])
            + "."
        )
    if observation.get("pack"):
        mates = [p for p in observation["pack"] if p != you]
        living = [p for p in mates if p in alive]
        lines.append(
            f"Your pack: {_names(mates)} ({len(living)} still alive). Do not attack them, but do not defend them too openly either."
        )
        if observation.get("wolf_votes"):
            lines.append(
                "Pack votes tonight: "
                + ", ".join(f"{v} -> {t}" for v, t in observation["wolf_votes"].items())
                + "."
            )
    if observation.get("seer_results"):
        lines.append(
            "Your visions: "
            + ", ".join(f"{p} is {r}" for p, r in observation["seer_results"].items())
            + "."
        )
    if "potions" in observation:
        left = [name for name, has in observation["potions"].items() if has]
        lines.append(f"Your potions left: {', '.join(left) or 'none'}.")
        if observation.get("wolf_victim"):
            lines.append(f"The wolves attacked {observation['wolf_victim']} tonight.")
    if observation.get("lovers"):
        lines.append(
            f"You are in love with {_names([p for p in observation['lovers'] if p != you])}; if one of you dies the other dies too."
        )
    if observation.get("protected_last_night"):
        lines.append(
            f"You protected {observation['protected_last_night']} last night and may not protect them again."
        )
    if observation.get("role_model"):
        lines.append(f"Your role model is {observation['role_model']}.")
    if observation.get("captain"):
        lines.append(f"Captain: {observation['captain']} (their vote counts double).")
    if observation.get("raven_mark"):
        lines.append(
            f"{observation['raven_mark']} carries the Raven's mark (2 extra votes against them)."
        )
    if observation.get("village_powers_lost"):
        lines.append("The village has lost its special powers.")
    if observation.get("may_vote") is False:
        lines.append("You may not vote today.")
    if phase == "day":
        votes = observation["votes_today"]
        if votes:
            lines.append(
                "Votes so far: "
                + ", ".join(f"{v} -> {t or 'abstain'}" for v, t in votes.items())
                + "."
            )
    if observation["your_turn"]:
        lines.append(
            f"Your move now: {observation['step']}. {len(others)} other player(s) alive to choose from."
        )
    return "\n".join(lines)
