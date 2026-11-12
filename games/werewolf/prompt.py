# ruff: noqa: E501  (lines of prose)
"""What a model reads about Werewolf: rules per prompt version and the situation summary.

- `werewolf-p1`: `rules.md` as it was, no summary.
- `werewolf-p2`: `rules_v2.md` and a short summary above the situation, worked out from the
  observation only: your role and what you win with, the phase, who lives, the pack, the votes,
  and your own secrets (seer results, potions, lovers). It states nothing the player does not see.
- `werewolf-p3`: `rules_v3.md` (what the first real matches taught: claim a Seer result early,
  silence is no evidence, do not copy the pack's words, vote for the player you named, what each
  role does with its power, brief thoughts) and the p2 summary plus a line of advice for this move.
- `werewolf-p4`: `rules_v4.md` (p3 plus a neutral "think about the whole match" section: a team
  aim, compare the legal options, keep facts apart from claims) and the p3 summary with the
  choices open to you now. Nothing in it is computed from the full game state.

All functions are pure.
"""

from collections.abc import Mapping
from importlib import resources
from typing import Any

from arena.agents.prompt import with_thought_in_the_call

VERSIONS = ("werewolf-p1", "werewolf-p1.1", "werewolf-p2", "werewolf-p3", "werewolf-p4")
DEFAULT_VERSION = "werewolf-p1"
_FILES = {
    "werewolf-p1": "rules.md",
    "werewolf-p2": "rules_v2.md",
    "werewolf-p3": "rules_v3.md",
    "werewolf-p4": "rules_v4.md",
}

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
    if version == "werewolf-p1.1":  # p1, with the thought where the system message asks for it
        return with_thought_in_the_call(rules_text("werewolf-p1"))
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


def move_advice(observation: Mapping[str, Any]) -> list[str]:
    """One or two lines of advice for the move the player is about to make (version p3).

    Built from the player's own observation only, and never names a role the player does not
    hold: a villager's advice to speak or vote is the same as a wolf's.
    """
    if not observation["your_turn"]:
        return []
    step = observation["step"]
    role = (observation["role"] or {}).get("id")
    visions = observation.get("seer_results") or {}
    alive = observation["alive"]
    if step == "speak":
        advice = [
            "Speak in 60-100 words: one concrete fact or suspect with its reason, in your own words.",
            "Silence or a short speech is not evidence; do not repeat another player's wording.",
        ]
        wolves = [
            p
            for p, r in visions.items()
            if r in ("werewolf", "prime_wolf", "white_wolf") and p in alive
        ]
        if wolves:
            advice.insert(
                0,
                f"You saw that {', '.join(wolves)} is a werewolf: say so now and name whom to vote for.",
            )
        return advice[:2]
    if step == "vote":
        advice = [
            "Vote for the player you named in your speech; if you change your mind, say so in the reason."
        ]
        wolves = [
            p
            for p, r in visions.items()
            if r in ("werewolf", "prime_wolf", "white_wolf") and p in alive
        ]
        if wolves:
            advice.append(f"Your own vision says {', '.join(wolves)} is a werewolf: vote for them.")
        return advice
    if step == "captain_vote":
        return [
            "Choose the player whose reasoning rests on facts; the captain's vote counts double."
        ]
    if step == "hunter":
        return ["Shoot your best wolf suspect, never a player confirmed as village."]
    if step == "wolf":
        return [
            "Pick someone dangerous (a likely power role or a sharp reasoner); the pack's majority decides."
        ]
    if step == "night":
        return {
            "seer": [
                "Check a player you know nothing about; do not check someone you already hold a result for."
            ],
            "witch": [
                "Heal the victim if they could be a power role; poison only a player the Seer named or a clear liar."
            ],
            "protector": [
                "Guard the player most likely to hold a power role; not the same player twice in a row."
            ],
            "raven": ["Mark the player you most suspect, never one you believe is village."],
            "little_girl": [
                "Spying risks being caught (15 %); spy at most two nights, then stay in bed."
            ],
            "cupid": ["Link two players who will protect each other."],
        }.get(role or "", [])
    return []


def situation_summary_v3(observation: Mapping[str, Any]) -> str:
    """The version p2 summary, and under it the advice for this move (version p3)."""
    summary = situation_summary(observation)
    advice = move_advice(observation)
    if not advice:
        return summary
    lines = "\n".join(f"- {line}" for line in advice)
    return f"{summary}\nFor this move:\n{lines}"


def legal_choices(observation: Mapping[str, Any]) -> list[str]:
    """The living players this move can name, from the observation only (version p4)."""
    if not observation["your_turn"]:
        return []
    you = observation["you"]
    step = observation["step"]
    pack = set(observation.get("pack") or [])
    if step in ("vote", "captain_vote", "hunter", "pass_captaincy"):
        return [p for p in observation["alive"] if p != you]
    if step == "wolf":
        return [p for p in observation["alive"] if p not in pack and p != you]
    return []


def situation_summary_v4(observation: Mapping[str, Any]) -> str:
    """The version p3 summary, and under it the players you can name now (version p4)."""
    summary = situation_summary_v3(observation)
    choices = legal_choices(observation)
    if not choices:
        return summary
    return f"{summary}\nYou can name: {_names(choices)}."
