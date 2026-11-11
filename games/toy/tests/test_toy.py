import asyncio

import pytest

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.engine.replay import replay
from arena.engine.types import Action, Event, EventSource, Reply
from games.toy.plugin import ToyGame

SEATS = ["p1", "p2", "p3", "p4"]


def bot_match(players, *, seed=1, settings=None, agents=None):
    plugin = ToyGame()
    bots = random_bots(plugin, players, seed)
    match = Match(plugin, bots | (agents or {}), seed=seed, settings=settings)
    placements = asyncio.run(match.run())
    return match, placements


def game_events(match):
    return [event for event in match.events if event.source is EventSource.GAME]


def dealt_hands(match):
    return {e.data["player"]: e.data["cards"] for e in match.events if e.type == "hand_dealt"}


def state_after_deal(hands):
    plugin = ToyGame()
    state = plugin.initial_state(list(hands), {})
    for player, cards in hands.items():
        deal = Event(
            source=EventSource.GAME, type="hand_dealt", data={"player": player, "cards": cards}
        )
        plugin.apply_event(state, deal)
    return plugin, state


@pytest.mark.parametrize("count", [2, 3, 4])
@pytest.mark.parametrize("hand_size", [1, 3, 5])
def test_bot_match_plays_every_card_and_ranks_by_tricks(count, hand_size):
    players = SEATS[:count]

    match, placements = bot_match(players, settings={"hand_size": hand_size})

    played = [e.data["card"] for e in match.events if e.type == "card_played"]
    assert sorted(played) == list(range(1, count * hand_size + 1))
    assert all(hand == [] for hand in match.state.hands.values())
    won = match.state.tricks_won
    assert sum(won.values()) == hand_size
    ranks = {p.player: p.rank for p in placements}
    assert min(ranks.values()) == 1
    for a in players:
        for b in players:
            assert (ranks[a] < ranks[b]) == (won[a] > won[b])


def test_highest_card_wins_the_trick_and_leads_the_next():
    match, _ = bot_match(SEATS[:3])

    events = game_events(match)
    tricks = [index for index, event in enumerate(events) if event.type == "trick_won"]
    assert len(tricks) == 3
    for index in tricks:
        won = events[index].data
        assert won["cards"][won["player"]] == max(won["cards"].values())
        if index + 1 < len(events):
            assert events[index + 1].data["player"] == won["player"]


def test_tied_players_share_a_rank_and_the_next_rank_is_skipped():
    plugin = ToyGame()
    state = plugin.initial_state(SEATS, {})
    for winner in ["p1", "p2", "p4"]:
        won = Event(source=EventSource.GAME, type="trick_won", data={"player": winner})
        plugin.apply_event(state, won)

    ranks = {placement.player: placement.rank for placement in plugin.results(state)}

    assert ranks == {"p1": 1, "p2": 1, "p3": 4, "p4": 1}


def test_same_seed_gives_the_same_match():
    first, first_placements = bot_match(SEATS, seed=11)
    second, second_placements = bot_match(SEATS, seed=11)

    assert first.events == second.events
    assert first.state == second.state
    assert first_placements == second_placements


def test_replaying_the_log_rebuilds_the_exact_end_state():
    match, _ = bot_match(SEATS, seed=11)

    assert replay(ToyGame(), match.events) == match.state


def test_replaying_up_to_the_deal_gives_the_dealt_hands():
    match, _ = bot_match(SEATS[:3], seed=11)
    deal_end = 1 + len(SEATS[:3])

    state = replay(ToyGame(), match.events[:deal_end])

    assert state.hands == dealt_hands(match)
    assert state.tricks_played == 0


def test_another_seed_deals_other_hands():
    assert dealt_hands(bot_match(SEATS, seed=11)[0]) != dealt_hands(bot_match(SEATS, seed=12)[0])


def test_deal_events_are_private_to_the_owner():
    match, _ = bot_match(SEATS[:3])

    for player in SEATS[:3]:
        deals_seen = [
            event.data["player"]
            for event in match.events
            if event.type == "hand_dealt" and event.is_visible_to(player)
        ]
        assert deals_seen == [player]


def test_observation_does_not_depend_on_other_players_hands():
    plugin, state = state_after_deal({"p1": [1, 5, 9], "p2": [2, 4, 6], "p3": [3, 7, 8]})
    _, swapped = state_after_deal({"p1": [1, 5, 9], "p2": [3, 7, 8], "p3": [2, 4, 6]})

    observation = plugin.get_observation(state, "p1")

    assert observation["hand"] == [1, 5, 9]
    assert observation == plugin.get_observation(swapped, "p1")


def test_observation_is_a_copy_of_the_state():
    plugin, state = state_after_deal({"p1": [1, 4], "p2": [2, 3]})

    plugin.get_observation(state, "p1")["hand"].clear()

    assert state.hands["p1"] == [1, 4]


class Clumsy:
    """Tries a card it does not hold, then plays what the wrapped bot would play."""

    def __init__(self, bot):
        self._bot = bot
        self.errors = []

    async def act(self, request):
        self.errors.append(request.error)
        if request.error is None:
            return Reply(action=Action(tool="play_card", arguments={"card": 99}))
        return await self._bot.act(request)


def clumsy_match():
    plugin = ToyGame()
    clumsy = Clumsy(random_bots(plugin, SEATS[:2], 3)["p1"])
    match, _ = bot_match(SEATS[:2], seed=3, agents={"p1": clumsy})
    return match, clumsy


def test_card_outside_the_hand_is_rejected_with_the_hand_in_the_message():
    match, clumsy = clumsy_match()

    hand = dealt_hands(match)["p1"]
    assert clumsy.errors[:2] == [None, f"Card 99 is not in your hand. Your hand: {hand}."]


def test_rejected_attempts_do_not_change_the_game():
    clean, _ = bot_match(SEATS[:2], seed=3)

    bumpy, _ = clumsy_match()

    assert any(event.type == "action_rejected" for event in bumpy.events)
    assert game_events(bumpy) == game_events(clean)
    assert bumpy.state == clean.state


def test_rules_for_model_prompts_come_with_the_game():
    rules = ToyGame().rules()

    assert "The highest card wins the trick." in rules
    assert "call `play_card` with one card from your hand" in rules
    # The title lives in `ToyGame.name` only.
    assert ToyGame.name == "High Card"
    assert "High Card" not in rules


@pytest.mark.parametrize("settings", [{"hand_size": 0}, {"hand_size": 6}, {"hand_size": "3"}])
def test_invalid_hand_size_is_refused(settings):
    with pytest.raises(ValueError, match="hand_size must be an integer from 1 to 5"):
        bot_match(SEATS[:2], settings=settings)


def test_unknown_setting_is_refused():
    with pytest.raises(ValueError, match=r"Unknown settings for toy: \['jokers'\]"):
        bot_match(SEATS[:2], settings={"jokers": 2})
