"""Werewolf analytics: votes, claims, accusations, stance per event and phase recaps."""

import asyncio
import json
from pathlib import Path

import pytest

from arena.agents.random_bot import random_bots
from arena.analytics import match_analytics
from arena.analytics.werewolf import read_speech
from arena.engine.match import Match
from arena.engine.types import MESSAGE, Event, EventSource
from arena.games import load_games

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "werewolf.json"
SEATS = [f"p{i}" for i in range(1, 9)]


def example():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return [Event(**{k: v for k, v in e.items() if k != "seq"}) for e in data["events"]]


def said(text, speaker="p1", names=None):
    return read_speech(text, speaker, SEATS, names or {})


def game(type, data, visible_to=None):
    return Event(source=EventSource.GAME, type=type, data=data, visible_to=visible_to)


def start():
    data = {"game": "werewolf", "players": SEATS, "settings": {}, "version": "1"}
    return Event(source=EventSource.ENGINE, type="match_started", data=data, visible_to=())


# --- reading speech -----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "role"),
    [
        ("Let's start. I'm p3, a villager. Plans?", "villager"),
        ("I am the seer and I checked p4.", "seer"),
        ("I'm p1, a simple villager with no night actions.", "villager"),
        ("Ich bin die Seherin.", "seer"),
        ("Ich bin ein einfacher Dorfbewohner.", "villager"),
        ("I am not the seer, but listen.", None),
        ("The seer is dead.", None),
    ],
)
def test_a_role_claim_is_read_from_first_person_speech(text, role):
    assert said(text)["claims"] == role


def test_seats_next_to_accusing_words_are_suspected_and_trusting_words_defend():
    reading = said("p7, your aggression is concerning. I trust p2. p5 is a wolf.")

    assert reading["suspects"] == ["p7", "p5"]  # in the order they were named
    assert reading["defends"] == ["p2"]


def test_a_negation_makes_a_sentence_neither_and_the_speaker_never_names_themselves():
    assert said("I don't suspect p3 at all.")["suspects"] == []
    assert said("I, p1, suspect p2.")["suspects"] == ["p2"]


def test_display_names_count_as_mentions_but_only_as_whole_words():
    names = {"p2": "Bo", "p3": "gpt-luna #1"}

    assert said("Bo is lying, and gpt-luna #1 too.", names=names)["suspects"] == ["p2", "p3"]
    assert said("Both of them are suspicious.", names=names)["suspects"] == []


# --- a match ------------------------------------------------------------------


def test_the_example_recaps_every_phase_with_its_deaths_and_votes():
    recap = match_analytics("werewolf", example(), False, {"p3": "Cy"})["recap"]

    assert [(r["kind"], r["number"]) for r in recap] == [
        ("night", 1),
        ("day", 1),
        ("night", 2),
        ("day", 2),
    ]
    assert recap[0]["text"]["en"] == "Night 1: p6 (witch) died, torn apart by the wolves."
    assert recap[1]["text"]["en"].startswith("Day 1: ")
    assert (
        "votes: Cy 7, p7 1; Cy (villager) died, executed by the village."
        in (recap[1]["text"]["en"])
    )
    assert recap[3]["text"]["de"].endswith("p8 (Seherin) starb, vom Dorf hingerichtet.")


def test_the_example_votes_are_facts_and_claims_show_a_changed_story():
    result = match_analytics("werewolf", example(), False)

    (day1, day2) = result["votes"]["days"]
    assert day1["tally"] == {"p3": 7, "p7": 1} and day1["executed"] == "p3"
    # The game's own count: the captain's vote may weigh double.
    assert sum(day1["tally"].values()) >= len(day1["votes"])
    assert day2["executed"] == "p8"
    assert result["votes"]["accuracy"] is None  # needs the roles
    claims = {(c["player"], c["role"]): c for c in result["claims"]}
    assert claims[("p7", "hunter")]["changed_from"] == "villager"
    assert claims[("p3", "villager")]["true_role"] == "villager"
    assert all(c["heuristic"] for c in result["claims"])
    assert not any(a["heuristic"] for a in result["accusations"] if a["source"] == "vote")


def test_vote_accuracy_and_the_roles_only_with_spoilers():
    full = match_analytics("werewolf", example(), True)

    accuracy = full["votes"]["accuracy"]
    # The village side only: the two wolves of the example are not judged.
    assert set(accuracy) == {"p1", "p3", "p5", "p7", "p8"}
    assert all(r["of"] >= 1 for r in accuracy.values())
    assert full["meta"]["roles"]["p2"] == "werewolf"
    assert match_analytics("werewolf", example(), False)["meta"]["roles"] is None


def test_a_vote_reason_belongs_to_the_vote_and_is_not_a_second_accusation():
    events = [
        start(),
        game("day_started", {"day": 1, "order": SEATS}),
        game("vote_cast", {"player": "p1", "target": "p2"}),
        game(MESSAGE, {"player": "p1", "text": "p2 is lying about being the seer."}),
    ]

    result = match_analytics("werewolf", events, False)

    vote = result["stance"][2]
    assert (vote["votes_for"], vote["reason_seq"], vote["heuristic"]) == ("p2", 3, False)
    assert [(a["target"], a["source"]) for a in result["accusations"]] == [("p2", "vote")]


def test_two_claims_of_one_unique_role_are_counterclaims_and_death_can_disprove_one():
    events = [
        start(),
        game("day_started", {"day": 1, "order": SEATS}),
        game(MESSAGE, {"player": "p1", "text": "I am the seer."}),
        game(MESSAGE, {"player": "p2", "text": "No, I am the seer!"}),
        game(MESSAGE, {"player": "p3", "text": "I'm a villager."}),
        game(MESSAGE, {"player": "p4", "text": "I'm a villager too."}),
        game("player_died", {"player": "p2", "cause": "executed", "role": "villager"}),
    ]

    claims = {c["player"]: c for c in match_analytics("werewolf", events, False)["claims"]}

    assert claims["p1"]["counterclaimed_by"] == ["p2"]
    assert claims["p2"]["counterclaimed_by"] == ["p1"]
    assert (claims["p2"]["disproved"], claims["p2"]["true_role"]) == (True, "villager")
    assert claims["p3"]["counterclaimed_by"] == []  # villagers are many


def test_wolf_chat_reaches_only_a_spectator():
    events = [
        start(),
        game("night_started", {"night": 1}),
        game(MESSAGE, {"player": "p2", "text": "p5 is a wolf, say it tomorrow."}, ["p2", "p4"]),
    ]

    assert match_analytics("werewolf", events, False)["stance"] == {}
    assert match_analytics("werewolf", events, True)["stance"][2]["suspects"] == ["p5"]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_bot_matches_give_consistent_votes_and_recaps_in_both_views(seed):
    plugin = load_games()["werewolf"]
    match = Match(plugin, random_bots(plugin, SEATS, seed), seed=seed)
    asyncio.run(match.run())

    for spoilers in (False, True):
        result = match_analytics("werewolf", match.events, spoilers)
        for day in result["votes"]["days"]:
            assert all(
                voter in SEATS and target in [*SEATS, None]
                for voter, target in day["votes"].items()
            )
            assert all(target in SEATS for target in day["tally"])
        assert all(a["target"] in SEATS and a["target"] != a["by"] for a in result["accusations"])
        assert len(result["recap"]) == len(result["phases"])
        for recap in result["recap"]:
            assert recap["text"]["en"] and recap["text"]["de"]


def test_a_claim_is_a_lie_with_spoilers_and_only_once_disproved_without():
    events = [
        start(),
        Event(
            source=EventSource.GAME,
            type="role_assigned",
            data={"player": "p1", "role": "werewolf"},
            visible_to=("p1",),
        ),
        Event(
            source=EventSource.GAME,
            type="role_assigned",
            data={"player": "p2", "role": "seer"},
            visible_to=("p2",),
        ),
        game("day_started", {"day": 1, "order": SEATS}),
        game(MESSAGE, {"player": "p1", "text": "I'm a simple villager."}),
        game(MESSAGE, {"player": "p2", "text": "I am the seer."}),
    ]

    full = {c["player"]: c["lie"] for c in match_analytics("werewolf", events, True)["claims"]}
    public = {c["player"]: c["lie"] for c in match_analytics("werewolf", events, False)["claims"]}

    assert full == {"p1": True, "p2": False}
    assert public == {"p1": None, "p2": None}  # nobody has died yet: unknown
    dead = [*events, game("player_died", {"player": "p1", "cause": "executed", "role": "werewolf"})]
    assert {c["player"]: c["lie"] for c in match_analytics("werewolf", dead, False)["claims"]} == {
        "p1": True,
        "p2": None,
    }


def test_the_report_awards_the_most_deceptive_and_the_most_accused():
    awards = match_analytics("werewolf", example(), True)["report"]["at_a_glance"]["awards"]

    by_id = {a["id"]: a for a in awards}
    assert by_id["most_deceptive"]["seat"] == "p7"
    assert by_id["most_deceptive"]["text"]["en"] == "Most deceptive: p7, 1 false role claim"
    assert by_id["most_accused"]["heuristic"] is True
    # Nobody on the village side voted for a wolf in the example: no "sharpest voter".
    assert "most_accurate_voter" not in by_id
    hidden = match_analytics("werewolf", example(), False)["report"]["at_a_glance"]["awards"]
    assert "most_deceptive" not in {a["id"] for a in hidden}  # no death disproved a claim


def test_suspicion_over_time_counts_each_days_votes_and_accusations_per_player():
    result = match_analytics("werewolf", example(), False)

    day1, day2 = result["suspicion"]
    assert [d["day"] for d in result["suspicion"]] == [1, 2]
    ballots = result["votes"]["days"][0]["votes"]
    assert day1["received"]["p3"]["votes"] == sum(t == "p3" for t in ballots.values())
    assert day1["most_suspected"] == ["p3"] and day2["most_suspected"] == ["p8"]
    for day in result["suspicion"]:
        for counts in day["received"].values():
            assert counts["total"] == counts["votes"] + counts["speech"]


def test_suspicion_leaves_out_the_night_and_counts_a_vote_reason_once():
    events = [
        start(),
        game("night_started", {"night": 1}),
        game(MESSAGE, {"player": "p2", "text": "p5 is suspicious, kill p5."}, ["p2", "p4"]),
        game("day_started", {"day": 1}),
        game(MESSAGE, {"player": "p1", "text": "I suspect p6, he is lying."}),
        game("vote_cast", {"player": "p1", "target": "p6"}),
        game(MESSAGE, {"player": "p1", "text": "p6 is the wolf, I am sure."}),
    ]

    (day,) = match_analytics("werewolf", events, True)["suspicion"]

    assert day["day"] == 1 and "p5" not in day["received"]  # the wolves' night chat
    assert day["received"]["p6"] == {"votes": 1, "speech": 1, "total": 2}


def test_bussing_shows_how_often_a_wolf_votes_for_a_fellow_wolf_with_spoilers_only():
    full = match_analytics("werewolf", example(), True)["votes"]
    public = match_analytics("werewolf", example(), False)["votes"]

    wolves = {"p2", "p4"}  # the example's two wolves
    assert set(full["bussing"]) == wolves
    for wolf, share in full["bussing"].items():
        cast = [d["votes"][wolf] for d in full["days"] if d["votes"].get(wolf)]
        assert (share["n"], share["of"]) == (sum(t in wolves for t in cast), len(cast))
    assert public["bussing"] is None
