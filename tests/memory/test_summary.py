"""The template summary of a match from one player's view."""

import pytest

from arena.engine.types import Placement
from arena.memory.facts import Fact
from arena.memory.summary import MatchView, TemplateSummarizer, _ordinal
from arena.memory.trust import load_rules


def view(**changes):
    base = dict(
        game_name="Liar's Deck",
        game_id="liars_deck",
        me="p1",
        names={"p1": "Ann", "p2": "Bob", "p3": "Cara"},
        placements=[
            Placement(player="p3", rank=1),
            Placement(player="p1", rank=2),
            Placement(player="p2", rank=3),
        ],
        facts=[],
    )
    return MatchView(**{**base, **changes})


def test_a_summary_names_the_game_the_opponents_and_the_place():
    text = TemplateSummarizer(load_rules()).summarize(view())

    assert text == "Liar's Deck against Bob, Cara: I finished 2nd of 3."


def test_a_summary_tells_what_the_player_saw_of_each_opponent_at_most_twice():
    facts = [
        Fact(observer="p1", about="p2", kind="accused_me_falsely", round=1),
        Fact(observer="p1", about="p2", kind="caught_lying", round=2),
        Fact(observer="p1", about="p2", kind="caught_lying", round=4),
        Fact(observer="p1", about="p3", kind="honest_when_called", round=3),
    ]

    text = TemplateSummarizer(load_rules()).summarize(view(facts=facts))

    assert text == (
        "Liar's Deck against Bob, Cara: I finished 2nd of 3. "
        "Bob called me a liar in round 1 when I told the truth; caught lying in round 2. "
        "Cara told the truth in round 3 when I called them out."
    )


def test_a_match_without_placements_has_no_place():
    text = TemplateSummarizer(load_rules()).summarize(view(placements=[]))

    assert text == "Liar's Deck against Bob, Cara."


@pytest.mark.parametrize(
    ("rank", "text"),
    [
        (1, "1st"),
        (2, "2nd"),
        (3, "3rd"),
        (4, "4th"),
        (11, "11th"),
        (12, "12th"),
        (13, "13th"),
        (21, "21st"),
        (22, "22nd"),
    ],
)
def test_ordinals(rank, text):
    assert _ordinal(rank) == text
