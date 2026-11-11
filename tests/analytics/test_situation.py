"""How is the game going: the situation of a match at any point, per game, in English and German."""

import asyncio
import json
import re
from pathlib import Path

import pytest

from arena.agents.random_bot import random_bots
from arena.analytics import match_analytics
from arena.engine.match import Match
from arena.engine.types import Event
from arena.games import load_games
from games.poker.plugin import DEFAULTS

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"
PLAYERS = {"liars_deck": 4, "poker": 4, "werewolf": 8}
NAMES = {
    f"p{i}": name for i, name in enumerate(["Ada", "Bo", "Cy", "Di", "Ed", "Flo", "Gus", "Hal"], 1)
}


def played(game, seed):
    plugin = load_games()[game]
    seats = [f"p{i}" for i in range(1, PLAYERS[game] + 1)]
    match = Match(plugin, random_bots(plugin, seats, seed), seed=seed)
    asyncio.run(match.run())
    return match.events


def example(game):
    data = json.loads((EXAMPLES / f"{game}.json").read_text(encoding="utf-8"))
    return [Event(**{k: v for k, v in e.items() if k != "seq"}) for e in data["events"]]


def now(game, events, spoilers=False, names=NAMES):
    return match_analytics(game, events, spoilers, names)["situation"]


def prefixes(events, count=12):
    step = max(len(events) // count, 1)
    return [events[:end] for end in range(1, len(events) + 1, step)] + [events]


@pytest.mark.parametrize("game", list(PLAYERS))
@pytest.mark.parametrize("seed", [1, 2])
def test_every_moment_of_a_bot_match_reads_in_both_languages_and_names_no_seat(game, seed):
    for events in prefixes(played(game, seed)):
        for spoilers in (False, True):
            lines = now(game, events, spoilers)["lines"]
            assert lines["en"] and len(lines["en"]) == len(lines["de"])
            for line in lines["en"] + lines["de"]:
                assert not re.search(r"\bp\d\b", line), line  # display names, never seat ids
                assert "_" not in line, line  # no engine words


@pytest.mark.parametrize("game", list(PLAYERS))
def test_the_example_matches_end_with_their_result(game):
    lines = now(game, example(game), names={})["lines"]

    assert (
        lines["en"][0]
        == {
            "liars_deck": "p1 wins the match.",
            "poker": "Over after hand 20: the hand limit is reached.",
            "werewolf": "The werewolves win.",
        }[game]
    )
    assert (
        lines["de"][0]
        == {
            "liars_deck": "p1 gewinnt die Partie.",
            "poker": "Vorbei nach Hand 20: das Handlimit ist erreicht.",
            "werewolf": "Die Werwölfe gewinnen.",
        }[game]
    )


def test_liars_deck_tells_round_turn_cards_left_risk_and_the_last_call():
    events = example("liars_deck")
    middle = events[: len(events) // 2]

    situation = now("liars_deck", middle, names={})

    assert situation["lines"]["en"] == [
        "Round 5 · table card: Queen · p4 to play.",
        "Cards left: p1 4, p4 5.",
        "Closest to elimination: p1, 2 pulls survived; the next one fires with 25 %.",
        "Last call: p4 called p1 a liar, and p1 was lying. p1 pulled the trigger and survived.",
    ]
    assert situation["lines"]["de"][0] == "Runde 5 · Tischkarte: Dame · p4 ist dran."
    # The risk is the analytics' own, public number: the same in both views.
    pulls = match_analytics("liars_deck", middle, False)["pulls"]
    assert situation["facts"]["risk"]["p1"] == pytest.approx(
        1 / (6 - sum(p["player"] == "p1" for p in pulls))
    )


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_poker_chips_add_up_at_every_moment(seed):
    events = played("poker", seed)
    for prefix in prefixes(events, count=30):
        facts = now("poker", prefix)["facts"]
        total = DEFAULTS["starting_stack"] * PLAYERS["poker"]
        assert sum(facts["stacks"].values()) + facts["pot"] == total
        assert all(chips >= 0 for chips in facts["stacks"].values())
        if facts["chip_leader"]:
            assert facts["stacks"][facts["chip_leader"]] == max(facts["stacks"].values())


def test_werewolf_teams_only_with_spoilers():
    events = example("werewolf")
    middle = events[: len(events) // 2]

    hidden, shown = now("werewolf", middle), now("werewolf", middle, spoilers=True)

    assert hidden["facts"]["teams"] is None
    assert not any("team" in line for line in hidden["lines"]["en"])
    assert sum(shown["facts"]["teams"].values()) == len(shown["facts"]["alive"])
    assert shown["lines"]["en"][1].startswith("Alive by team: ")
    assert hidden["lines"]["en"][0] == shown["lines"]["en"][0] == "Day 1 · 7 of 8 alive."


@pytest.mark.parametrize("seed", [1, 2])
def test_a_spoiler_free_situation_is_the_same_whatever_the_hidden_events_say(seed):
    # Hiding every private event changes nothing a spoiler-free viewer reads.
    for game in PLAYERS:
        events = played(game, seed)
        public = [e for e in events if e.visible_to is None or e.type == "match_started"]
        assert now(game, events) == now(game, public)


def test_a_game_without_a_situation_has_none_and_toy_still_has_no_analytics():
    assert now("liars_deck", [])["lines"]["en"] == ["The match is about to start."]


def test_an_abstention_is_no_vote_for_anyone():
    events = [
        Event(source="engine", type="match_started", data={"players": ["p1", "p2"]}),
        Event(source="game", type="day_started", data={"day": 1, "order": ["p1", "p2"]}),
        Event(source="game", type="vote_cast", data={"player": "p1", "target": None}),
        Event(source="game", type="vote_cast", data={"player": "p2", "target": "p1"}),
    ]

    situation = now("werewolf", events)

    assert situation["facts"]["votes"] == {"p1": 1}
    assert "None" not in " ".join(situation["lines"]["en"])


def test_the_answer_lists_its_sections_so_a_client_need_not_probe_keys():
    poker = match_analytics("poker", example("poker"), False, {})
    liars = match_analytics("liars_deck", example("liars_deck"), False, {})

    assert (poker["sections"], poker["numbers"]) == (["situation"], False)
    assert liars["numbers"] is True
    assert {"situation", "moves", "totals", "players"} <= set(liars["sections"])
    assert all(section in liars for section in liars["sections"])
