"""p1.1: p1 with its sentence about thoughts made to agree with the system message."""

import pytest

from arena.agents.prompt import (
    P1_1_THOUGHT_SENTENCE,
    P1_THOUGHT_SENTENCE,
    with_thought_in_the_call,
)
from arena.games import load_games

GAMES = ["liars_deck", "poker", "werewolf"]


@pytest.mark.parametrize("game", GAMES)
def test_p1_1_is_p1_with_one_sentence_changed_and_p1_is_untouched(game):
    plugin = load_games()[game]
    p1 = plugin.rules({"prompt_version": f"{game}-p1"})
    p1_1 = plugin.rules({"prompt_version": f"{game}-p1.1"})

    assert P1_THOUGHT_SENTENCE in p1  # the baseline keeps what earlier experiments read
    assert P1_THOUGHT_SENTENCE not in p1_1 and P1_1_THOUGHT_SENTENCE in p1_1
    assert p1_1.replace(P1_1_THOUGHT_SENTENCE, P1_THOUGHT_SENTENCE) == p1
    assert plugin.prompt_version({"prompt_version": f"{game}-p1.1"}) == f"{game}-p1.1"


@pytest.mark.parametrize("game", GAMES)
def test_p1_1_has_no_summary_like_p1(game):
    plugin = load_games()[game]

    assert plugin.situation_summary({}, {"prompt_version": f"{game}-p1.1"}) is None


def test_rules_without_the_sentence_are_refused():
    with pytest.raises(ValueError, match="sentence about thoughts"):
        with_thought_in_the_call("Some rules without it.")
