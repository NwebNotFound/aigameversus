"""Jev step 3, the post-match referee: moments by rule, only what a player saw, strict answers."""

import asyncio
import json

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.engine.types import Event, EventSource
from arena.games import load_games
from arena.jev.client import JevError, parse
from arena.jev.referee import check_scores, moments, request_of, tags_of


def engine(type_, data, visible_to=None):
    return Event(source=EventSource.ENGINE, type=type_, data=data, visible_to=visible_to)


def move(player, tool, arguments=None, rejected=False):
    kind = "action_rejected" if rejected else "action_accepted"
    data = {"player": player, "tool": tool, "arguments": arguments or {}}
    if rejected:
        data["error"] = "not now"
    return engine(kind, data, (player,))


def thought(player, text):
    return engine("thought", {"player": player, "text": text}, ())


def test_moments_are_chosen_by_rule_round_robin_over_categories_and_counted():
    events = [
        thought("p1", "I call."),
        move("p1", "call_liar"),
        move("p2", "call_liar"),  # a bot: never a moment
        move("p1", "table_talk", {"text": "I have no kings."}),
        move("p1", "play_cards!", rejected=True),
        thought("p1", "Two kings."),
        move("p1", "play_cards", {"card_ids": [1, 2]}),
        move("p1", "call_liar"),
        move("p1", "call_liar"),
        move("p1", "table_talk", {"text": "Trust me."}),
    ]

    picked = moments(events, {"p1"}, limit=5)

    assert [(m["seq"], m["category"]) for m in picked["moments"]] == [
        (1, "decision"),
        (3, "talk"),
        (4, "rejected"),
        (6, "decision"),
        (9, "talk"),
    ]
    assert picked["counts"] == {
        "decision": {"available": 4, "chosen": 2},
        "talk": {"available": 2, "chosen": 2},
        "rejected": {"available": 1, "chosen": 1},
    }
    assert picked["absent"] == []
    by_seq = {m["seq"]: m["thought"] for m in picked["moments"]}
    assert (by_seq[1], by_seq[6], by_seq[9]) == ("I call.", "Two kings.", None)  # its own only
    assert moments(events, {"p1"}) == picked  # the same match, the same moments


def test_a_category_without_moves_is_named_absent():
    picked = moments([thought("p1", "x"), move("p1", "call_liar")], {"p1"})

    assert picked["absent"] == ["talk", "rejected"]


def test_the_state_holds_only_what_the_player_could_see_then():
    plugin = load_games()["werewolf"]
    seats = [f"p{i}" for i in range(1, 9)]
    match = Match(plugin, random_bots(plugin, seats, 4), seed=4, settings={})
    asyncio.run(match.run())
    events = match.events

    picked = moments(events, {"p1"})
    state, _ = request_of("werewolf", events, picked, set())

    sent = json.dumps(state, ensure_ascii=False)
    for moment in picked["moments"]:
        seen = state["moments"][f"m{picked['moments'].index(moment) + 1}"]["what_the_player_saw"]
        for event in events[: moment["seq"]]:
            if event.visible_to is not None and "p1" not in event.visible_to and event.data:
                line = json.dumps({"type": event.type, **event.data}, ensure_ascii=False)
                assert line not in seen
    others = [e.data for e in events if e.type == "role_assigned" and e.data["player"] != "p1"]
    for role in others:
        assert json.dumps({"type": "role_assigned", **role}, ensure_ascii=False) not in sent


def test_the_questions_fit_each_moment_and_the_engine_checked_talk_gets_no_lie_question():
    events = [
        thought("p1", "I bluff."),
        move("p1", "table_talk", {"text": "I have no kings."}),
        move("p1", "table_talk", {"text": "Trust me."}),
        move("p1", "call_liar"),
    ]
    picked = moments(events, {"p1"})

    _, questions = request_of("liars_deck", events, picked, checked={(1, "p1")})

    assert sorted(questions) == [
        "m1_consistent",  # talk with a thought
        "m1_persuasive",  # no m1_lie: the engine's talk check judged seq 1
        "m2_lie",
        "m2_persuasive",
    ]
    assert questions["m2_persuasive"]["type"] == "score"
    assert len(questions["m2_persuasive"]["criteria"]) == 5


def answer(questions, score=None):
    answers = {}
    for key, question in questions.items():
        if question["type"] == "noul":
            answers[key] = {"type": "noul", "probability": 0.8}
        else:
            answers[key] = {
                "type": "score",
                "score": 3.0,
                "probabilities": score or [0.1, 0.2, 0.4, 0.2, 0.1],
            }
    return {"answers": answers, "usage": {"input_tokens": 900, "cost": 0.00004}}


def test_the_tags_carry_the_raw_distributions_unvalidated():
    events = [thought("p1", "Why not."), move("p1", "table_talk", {"text": "I am the seer."})]
    picked = moments(events, {"p1"})
    _, questions = request_of("werewolf", events, picked, set())

    result = parse(answer(questions), questions)
    check_scores(result, questions)
    (tag,) = tags_of(result, picked)

    assert tag["validated"] is False
    assert (tag["consistent_probability"], tag["lie_probability"]) == (0.8, 0.8)
    assert tag["persuasiveness"] == {"probabilities": [0.1, 0.2, 0.4, 0.2, 0.1], "expected": 3.0}


@pytest.mark.parametrize(
    "score",
    [
        [0.5, 0.5],  # not one per level
        [0.5, 0.5, 0.5, 0.0, 0.0],  # sums to 1.5
        [1.2, -0.2, 0.0, 0.0, 0.0],  # outside [0, 1]
    ],
)
def test_a_score_answer_that_is_not_a_distribution_over_the_levels_is_refused(score):
    events = [thought("p1", "x"), move("p1", "speak", {"text": "Vote p3."})]
    picked = moments(events, {"p1"})
    _, questions = request_of("werewolf", events, picked, set())

    with pytest.raises(JevError) as refused:
        check_scores(parse(answer(questions, score), questions), questions)

    assert refused.value.reason == "bad_answer"
