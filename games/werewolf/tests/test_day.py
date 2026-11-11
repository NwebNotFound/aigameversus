import pytest

from games.werewolf.plugin import Werewolf
from games.werewolf.tests.test_plugin import CLASSIC, Table, bot_match


def night_without_deaths(table, *, victim="f"):
    table.act("b", "seer_check", target="f")
    table.act("a", "wolf_kill", target=victim)
    table.act("e", "wolf_kill", target=victim)
    table.act("c", "witch_act", heal=True, poison_target=None)


def elect(table, votes):
    while table.state.queue and table.state.queue[0].kind == "captain_vote":
        voter = table.turn[0]
        table.act(voter, "elect_captain", target=votes[voter])


def narrations(table):
    return [(e.data["key"], e.data["text"]) for e in table.of_type("narration")]


# --- captain -----------------------------------------------------------------------


def test_the_village_elects_a_captain_before_the_first_discussion():
    table = Table(CLASSIC, captain=True)
    night_without_deaths(table)

    assert [s.kind for s in table.state.queue[:8]] == ["captain_vote"] * 8
    elect(table, dict.fromkeys("abcdefgh", "f") | {"a": "b", "e": "b"})

    assert table.of_type("captain_elected")[0].data == {"player": "f", "votes": {"f": 6, "b": 2}}
    assert table.state.captain == "f"
    assert table.state.queue[0].kind == "speak"
    assert table.plugin.get_observation(table.state, "a")["captain"] == "f"


def test_a_tied_election_is_settled_by_the_seed():
    def elected(seed_start):
        table = Table(CLASSIC, captain=True, speaking_start=seed_start)
        night_without_deaths(table)
        elect(table, {p: ("f" if i % 2 else "g") for i, p in enumerate("abcdefgh")})
        return table.state.captain

    assert elected(0) in ("f", "g")
    assert elected(0) == elected(0)


def test_only_day_one_has_an_election():
    for seed in range(1, 8):
        match, _ = bot_match(8, seed=seed, settings={"captain": True})
        days = [e for e in match.events if e.type == "day_started"]
        elections = [e for e in match.events if e.type == "captain_elected"]

        assert len(elections) == (1 if days else 0)
        if days:
            first_day = match.events.index(days[0])
            assert match.events.index(elections[0]) > first_day


def test_the_captains_vote_counts_double():
    table = Table(CLASSIC, captain=True)
    night_without_deaths(table)
    elect(table, dict.fromkeys("abcdefgh", "g"))
    table.talk_through_day()

    # 3 votes for e against 2 for a, but the captain g votes a: 3 against 4.
    table.vote({"b": "e", "c": "e", "d": "e", "f": "a", "h": "a", "g": "a"})

    assert table.of_type("vote_result")[0].data["counts"] == {"e": 3, "a": 4}
    assert table.of_type("vote_result")[0].data["executed"] == "a"


def test_a_dying_captain_names_a_successor():
    table = Table(CLASSIC, captain=True)
    night_without_deaths(table)
    elect(table, dict.fromkeys("abcdefgh", "g"))
    table.talk_through_day()

    table.vote(dict.fromkeys("abcdefh", "g"))

    assert table.turn == ["g"] and set(table.tools("g")) == {"pass_captaincy"}
    table.act("g", "pass_captaincy", target="b")
    assert table.state.captain == "b"
    assert table.of_type("captain_passed")[0].data == {"from": "g", "to": "b"}


def test_a_captain_who_is_the_hunter_shoots_first_then_passes_on():
    table = Table(CLASSIC, captain=True)
    night_without_deaths(table)
    elect(table, dict.fromkeys("abcdefgh", "d"))
    table.talk_through_day()
    table.vote(dict.fromkeys("abcefgh", "d"))

    assert [s.kind for s in table.state.queue] == ["hunter", "pass_captaincy"]
    table.act("d", "hunter_shoot", target="a")
    table.act("d", "pass_captaincy", target="c")

    assert table.state.captain == "c"
    assert table.state.night == 2


def test_captain_can_be_switched_off():
    table = Table(CLASSIC, captain=False)
    night_without_deaths(table)

    assert table.state.queue[0].kind == "speak"


# --- narrator ------------------------------------------------------------------


def test_the_narrator_speaks_at_every_turn_of_the_game_in_english():
    table = Table(CLASSIC, captain=True, language="en")
    table.act("b", "seer_check", target="f")
    table.act("a", "wolf_kill", target="b")
    table.act("e", "wolf_kill", target="b")
    table.act("c", "witch_act", heal=False, poison_target=None)
    elect(table, dict.fromkeys("acdefgh", "c"))
    table.talk_through_day()
    table.vote({})

    assert narrations(table) == [
        ("morning_deaths", "Dawn breaks. Found dead: b (Seherin)."),
        ("captain_elected", "c is now the village captain."),
        ("no_execution", "The village cannot agree. Nobody dies today."),
        ("night_falls", "Night 2 falls. The village sleeps."),
    ]
    assert all(e.visible_to is None for e in table.of_type("narration"))


def test_german_is_the_default_language():
    match, _ = bot_match(8, seed=2)
    lines = [e.data for e in match.events if e.type == "narration"]

    assert lines[0] == {
        "key": "night_falls",
        "data": {"night": 1},
        "text": "Nacht 1 bricht herein. Das Dorf schläft.",
        "language": "de",
    }
    assert lines[-1]["key"] == "game_over"


def test_execution_narration_names_the_role():
    table = Table(CLASSIC)
    night_without_deaths(table)
    table.talk_through_day()

    table.vote(dict.fromkeys("bcdfgh", "a"))

    assert ("execution", "The village has decided: a is executed. a was Werwolf.") in narrations(
        table
    )


def test_unknown_language_is_rejected():
    with pytest.raises(ValueError, match="language must be one of de, en"):
        Werewolf().initial_state([f"p{i}" for i in range(8)], {"language": "fr"})
