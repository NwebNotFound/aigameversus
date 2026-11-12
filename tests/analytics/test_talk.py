"""Table talk is checked against the engine's cards and roles, without a model."""

import asyncio

import pytest

from arena.agents.random_bot import random_bots
from arena.analytics.talk import _hold_claims, talk_checks
from arena.engine.match import Match
from arena.engine.types import MESSAGE, Event, EventSource
from games.liars_deck.plugin import LiarsDeck
from games.poker.plugin import Poker
from games.werewolf.plugin import Werewolf


def game(type, data, visible_to=None):
    return Event(source=EventSource.GAME, type=type, data=data, visible_to=visible_to)


def say(player, text):
    return Event(source=EventSource.GAME, type=MESSAGE, data={"player": player, "text": text})


def numbered(events):
    return list(enumerate(events))


# --- Liar's Deck ----------------------------------------------------------------------


def liars_round(talk, played, hand=("K1", "K2", "Q1", "A1", "J1")):
    """p1 says `talk`, then plays `played`; the table card is king."""
    return numbered(
        [
            game("round_started", {"round": 1, "table_card": "king", "starter": "p1",
                                   "hand_size": 5, "players": ["p1", "p2"]}),
            game("hand_dealt", {"player": "p1", "cards": list(hand)}, visible_to=["p1"]),
            say("p1", talk),
            game("cards_played", {"player": "p1", "count": len(played)}),
            game("cards_hidden", {"player": "p1", "cards": list(played)}, visible_to=["p1"]),
        ]
    )  # fmt: skip


def tags(log, game_id="liars_deck", spoilers=True):
    return talk_checks(game_id, log, spoilers)["tags"]


def test_a_claim_of_no_kings_is_false_when_the_hand_holds_kings():
    found = tags(liars_round("I have no kings at all.", ["Q1"]))

    assert [(t["kind"], t["verdict"]) for t in found] == [("hand_claim", "false")]
    assert "2 king" in found[0]["evidence"] and found[0]["player"] == "p1"
    assert found[0]["heuristic"] is True


def test_a_true_statement_about_the_hand_is_checked_as_true():
    found = tags(liars_round("I only have one queen left.", ["K1"]))

    assert [t["verdict"] for t in found] == ["true"]
    assert found[0]["claim"] == "holds exactly 1 queen(s)"


def test_at_least_and_exact_readings_differ():
    log = liars_round("I have two kings.", ["K1"])
    assert [t["verdict"] for t in tags(log)] == ["true"]  # at least two: it holds two

    log = liars_round("I just have two aces.", ["K1"])
    assert [t["verdict"] for t in tags(log)] == ["false"]  # exactly two: it holds one


def test_the_words_with_a_play_are_checked_against_the_cards_played():
    lie = tags(liars_round("Honest play, I swear. I'm being honest.", ["Q1", "K1"]))
    truth = tags(liars_round("I am telling the truth.", ["K1", "J1"]))

    assert [(t["kind"], t["verdict"]) for t in lie] == [("honesty_claim", "false")]
    assert "Q1" in lie[0]["evidence"] and "table card: king" in lie[0]["evidence"]
    assert [t["verdict"] for t in truth] == ["true"]  # a joker counts as the table card


def test_a_count_and_rank_said_with_the_play_must_match_the_cards():
    found = tags(liars_round("Playing two kings.", ["K1", "Q1"]))

    assert [(t["kind"], t["verdict"], t["claim"]) for t in found] == [
        ("play_claim", "false", "played 2 king(s)")
    ]
    assert [t["verdict"] for t in tags(liars_round("Putting down two kings.", ["K1", "K2"]))] == [
        "true"
    ]


def test_questions_and_other_players_words_are_not_checked():
    assert tags(liars_round("Do you think I have no kings?", ["Q1"])) == []
    assert tags(liars_round("p2 has no kings, I bet.", ["Q1"])) == []
    assert tags(liars_round("Hmm, hard to say.", ["Q1"])) == []


def test_without_spoilers_the_hidden_cards_give_no_tags():
    result = talk_checks("liars_deck", liars_round("I have no kings.", ["Q1"]), spoilers=False)

    assert result["available"] is False and result["tags"] == []


def test_hold_claims_read_the_usual_phrases():
    assert _hold_claims("i've got three queens left")[0][:3] == ("queen", 3, True)
    assert _hold_claims("I don't have any aces")[0][:3] == ("ace", 0, True)
    assert _hold_claims("i'm out of kings")[0][:3] == ("king", 0, True)
    assert _hold_claims("I have a joker")[0][:3] == ("joker", 1, False)
    assert _hold_claims("nothing to see") == []


# --- Poker ----------------------------------------------------------------------------


def poker_log(talk, hole, board_cards=()):
    events = [
        game("hand_started", {"hand": 1, "button": "p1", "players": ["p1", "p2"], "big_blind": 20}),
        game("hole_dealt", {"player": "p1", "cards": list(hole)}, visible_to=["p1"]),
    ]
    if board_cards:
        events.append(
            game("street_started", {"street": "flop", "order": [], "cards": list(board_cards)})
        )
    events.append(say("p1", talk))
    return numbered(events)


@pytest.mark.parametrize(
    ("talk", "hole", "board", "verdict"),
    [
        ("I have a flush.", ["Ah", "Kh"], ["2h", "7h", "9h"], "true"),
        ("I have a flush.", ["Ah", "Kd"], ["2h", "7h", "9h"], "false"),
        ("I have two pair, careful.", ["As", "7d"], ["Ah", "7c", "2d"], "true"),
        ("I've got a pair.", ["As", "7d"], ["Kh", "9c", "2d"], "false"),
        ("I have a pair of aces.", ["As", "Ad"], [], "true"),
        ("I have nothing, folks.", ["As", "7d"], ["Kh", "9c", "2d"], "true"),
        ("I have nothing, folks.", ["As", "7d"], ["Ah", "9c", "2d"], "false"),
        ("I have a straight.", ["As", "Kd"], [], "false"),
        ("I have pocket kings.", ["Ks", "Kd"], [], "true"),
    ],
)
def test_poker_hand_statements_are_checked_against_hole_cards_and_board(talk, hole, board, verdict):
    found = tags(poker_log(talk, hole, board), "poker")

    assert [t["verdict"] for t in found] == [verdict], found
    assert found[0]["kind"] == "poker_hand_claim" and "hole" in found[0]["evidence"]


def test_a_board_pair_alone_is_no_pair_in_hand():
    found = tags(poker_log("I have a pair.", ["As", "7d"], ["Kh", "Kc", "2d"]), "poker")

    assert [t["verdict"] for t in found] == ["false"]


# --- Werewolf -------------------------------------------------------------------------


def werewolf_log():
    return numbered(
        [
            Event(source=EventSource.ENGINE, type="match_started", visible_to=(),
                  data={"game": "werewolf", "version": "1", "players": ["p1", "p2", "p3"],
                        "settings": {}, "seed": 1}),
            game("role_assigned", {"player": "p1", "role": "werewolf"}, visible_to=[]),
            game("role_assigned", {"player": "p2", "role": "seer"}, visible_to=[]),
            game("role_assigned", {"player": "p3", "role": "villager"}, visible_to=[]),
            game("day_started", {"day": 1, "order": ["p1", "p2", "p3"]}),
            say("p1", "I am the seer, trust me."),
            say("p2", "I am the seer and p1 lies."),
        ]
    )  # fmt: skip


def test_werewolf_role_claims_become_tags_with_the_true_role():
    found = tags(werewolf_log(), "werewolf")

    assert [(t["player"], t["verdict"]) for t in found] == [("p1", "false"), ("p2", "true")]
    assert found[0]["kind"] == "role_claim" and found[0]["claim"] == "is the seer"


def test_werewolf_without_spoilers_shows_only_claims_a_death_has_disproved():
    assert tags(werewolf_log(), "werewolf", spoilers=False) == []


# --- whole bot matches ----------------------------------------------------------------


def played(plugin, players, seed):
    match = Match(
        plugin, random_bots(plugin, [f"p{i}" for i in range(1, players + 1)], seed), seed=seed
    )
    asyncio.run(match.run())
    return numbered(match.events)


@pytest.mark.parametrize(
    ("name", "plugin", "players"),
    [("liars_deck", LiarsDeck, 3), ("poker", Poker, 3), ("werewolf", Werewolf, 8)],
)
def test_a_bot_match_gives_a_well_formed_answer_with_and_without_spoilers(name, plugin, players):
    log = played(plugin(), players, 3)

    for spoilers in (True, False):
        result = talk_checks(name, log, spoilers)
        assert result["game"] == name and isinstance(result["tags"], list)
        for tag in result["tags"]:
            assert tag["verdict"] in ("true", "false") and tag["seq"] >= 0 and tag["heuristic"]
    assert talk_checks("toy", log, True)["available"] is False


def test_private_werewolf_talk_is_never_quoted_without_spoilers():
    """Pack chat is a message with a visible_to list: no tag may quote it in the public view."""
    log = werewolf_log()
    secret = "Pack, listen: tomorrow I am the seer and I checked p3, a villager."
    private = Event(
        source=EventSource.GAME,
        type=MESSAGE,
        data={"player": "p1", "text": secret},
        visible_to=["p1", "p2"],
    )
    died = game("player_died", {"player": "p1", "cause": "executed", "role": "werewolf"})
    log = log[:5] + [(5, private)] + [(seq + 1, e) for seq, e in log[5:]] + [(0, died)]
    log = [(seq, e) for seq, (_, e) in enumerate(log)]

    full = talk_checks("werewolf", log, spoilers=True)["tags"]
    public = talk_checks("werewolf", log, spoilers=False)["tags"]

    assert any("Pack, listen" in t["quote"] for t in full)
    assert not any("Pack, listen" in t["quote"] for t in public)
    by_seq = dict(log)
    assert all(by_seq[t["seq"]].visible_to is None for t in public)
