"""Roles batch A: Cupid and the lovers, Protector, Little Girl, Elder, Village Idiot, Scapegoat."""

import pytest

from arena.engine.types import MESSAGE, Action
from games.werewolf import abilities
from games.werewolf.tests.test_plugin import Table


def wolves_take(table, target, wolves=("a",)):
    for wolf in wolves:
        table.act(wolf, "wolf_kill", target=target)


def deaths(table):
    return [(e.data["player"], e.data["cause"]) for e in table.of_type("player_died")]


def to_vote(table):
    table.talk_through_day()


# --- Cupid and the lovers ------------------------------------------------------


LOVE = {
    "a": "werewolf",
    "b": "cupid",
    "c": "villager",
    "d": "villager",
    "e": "villager",
    "f": "villager",
}


def test_cupid_acts_first_on_night_one_only():
    table = Table(LOVE)

    assert [s.player for s in table.state.queue] == ["b", "a"]
    table.act("b", "link_lovers", a="c", b="d")
    wolves_take(table, "e")
    to_vote(table)
    table.vote({})

    assert [s.player for s in table.state.queue] == ["a"]  # night 2: no Cupid step


def test_lovers_learn_each_other_privately():
    table = Table(LOVE)

    table.act("b", "link_lovers", a="c", b="d")

    revealed = table.of_type("love_revealed")[0]
    assert revealed.data == {"lovers": ["c", "d"]} and revealed.visible_to == ("c", "d")
    assert table.of_type("lovers_linked")[0].visible_to == ("b",)
    assert table.plugin.get_observation(table.state, "c")["lovers"] == ["c", "d"]
    assert "lovers" not in table.plugin.get_observation(table.state, "e")


def test_cupid_must_pick_two_different_players():
    table = Table(LOVE)
    action = Action(tool="link_lovers", arguments={"a": "c", "b": "c"})

    assert (
        table.plugin.validate(table.state, "b", action) == "Pick two different players as lovers."
    )


def test_a_lover_dies_of_grief():
    table = Table(LOVE)
    table.act("b", "link_lovers", a="c", b="d")

    wolves_take(table, "c")

    assert deaths(table) == [("c", "wolves"), ("d", "grief")]
    assert ("grief", "d dies of grief for c.") in [
        (e.data["key"], e.data["text"]) for e in table.of_type("narration")
    ]


def test_lovers_of_both_sides_win_as_the_last_pair():
    roles = {
        "a": "werewolf",
        "b": "cupid",
        "c": "villager",
        "d": "villager",
        "e": "villager",
        "f": "villager",
    }
    table = Table(roles)
    table.act("b", "link_lovers", a="a", b="c")  # a wolf and a villager
    wolves_take(table, "d")
    to_vote(table)
    table.vote({p: "e" for p in "abcf"})  # e executed: a, b, c, f left
    wolves_take(table, "f")
    to_vote(table)

    table.vote({"a": "b", "c": "b"})  # b executed: only the lovers a and c are left

    assert table.of_type("game_over")[0].data == {"winner": "lovers", "winners": ["a", "c"]}


def test_lover_chat_is_private_once_per_turn_and_does_not_end_it():
    table = Table(LOVE)
    table.act("b", "link_lovers", a="a", b="c")

    table.act("a", "lover_chat", text="Do not vote for me.")

    assert table.turn == ["a"]
    chat = [e for e in table.of_type(MESSAGE)][0]
    assert chat.data == {"player": "a", "text": "Do not vote for me."}
    assert chat.visible_to == ("a", "c")
    assert "lover_chat" not in table.tools("a")
    table.act("a", "wolf_kill", target="d")
    while table.turn != ["c"]:  # the day: speeches until it is the other lover's turn
        table.act(table.turn[0], "speak", text="Hm.")
    assert "lover_chat" in table.tools("c")


# --- Protector -------------------------------------------------------------------


GUARDED = {
    "a": "werewolf",
    "b": "protector",
    "c": "witch",
    "d": "villager",
    "e": "villager",
    "f": "villager",
}


def test_protector_saves_the_wolves_victim():
    table = Table(GUARDED)
    table.act("b", "protect", target="d")
    wolves_take(table, "d")

    table.act("c", "witch_act", heal=False, poison_target=None)

    assert deaths(table) == []
    assert table.of_type("protected")[0].visible_to == ("b",)


def test_protection_does_not_stop_poison():
    table = Table(GUARDED)
    table.act("b", "protect", target="d")
    wolves_take(table, "e")

    table.act("c", "witch_act", heal=False, poison_target="d")

    assert sorted(deaths(table)) == [("d", "poison"), ("e", "wolves")]


def test_protector_cannot_guard_the_same_player_twice_in_a_row():
    table = Table(GUARDED)
    table.act("b", "protect", target="b")
    wolves_take(table, "d")
    table.act("c", "witch_act", heal=False, poison_target=None)
    to_vote(table)
    table.vote({})

    choices = table.tools("b")["protect"].parameters["properties"]["target"]["enum"]
    assert "b" not in choices and "e" in choices
    assert table.plugin.get_observation(table.state, "b")["protected_last_night"] == "b"


# --- Little Girl ------------------------------------------------------------------


GIRL = {
    "a": "werewolf",
    "b": "little_girl",
    "c": "villager",
    "d": "villager",
    "e": "villager",
    "f": "villager",
}


def test_little_girl_may_learn_a_wolf(monkeypatch):
    monkeypatch.setattr(abilities, "SPY_FIND_CHANCE", 1.0)
    monkeypatch.setattr(abilities, "SPY_CAUGHT_CHANCE", 0.0)
    table = Table(GIRL)

    table.act("b", "spy")

    spied = table.of_type("spied")[0]
    assert spied.data == {"player": "b", "wolf": "a"} and spied.visible_to == ("b",)
    assert table.of_type("girl_caught") == []


def test_a_caught_little_girl_is_eaten_instead_of_the_victim(monkeypatch):
    monkeypatch.setattr(abilities, "SPY_FIND_CHANCE", 0.0)
    monkeypatch.setattr(abilities, "SPY_CAUGHT_CHANCE", 1.0)
    table = Table(GIRL)
    table.act("b", "spy")

    wolves_take(table, "c")

    assert table.of_type("spied")[0].data["wolf"] is None
    assert table.of_type("girl_caught")[0].visible_to == ()
    assert deaths(table) == [("b", "caught_spying")]


def test_staying_in_bed_risks_nothing():
    table = Table(GIRL)

    table.act("b", "stay_in_bed")
    wolves_take(table, "c")

    assert table.of_type("spied") == [] and deaths(table) == [("c", "wolves")]


# --- Elder --------------------------------------------------------------------------


ELDER = {
    "a": "werewolf",
    "b": "elder",
    "c": "seer",
    "d": "hunter",
    "e": "villager",
    "f": "villager",
    "g": "villager",
}


def test_elder_survives_the_first_wolf_attack_only():
    table = Table(ELDER)
    table.act("c", "seer_check", target="a")
    wolves_take(table, "b")

    assert deaths(table) == []
    assert table.of_type("elder_survived")[0].visible_to == ("b",)
    to_vote(table)
    table.vote({})
    table.act("c", "seer_check", target="e")
    wolves_take(table, "b")
    assert deaths(table) == [("b", "wolves")]


def test_executing_the_elder_strips_the_village_of_its_powers():
    table = Table(ELDER)
    table.act("c", "seer_check", target="a")
    wolves_take(table, "e")
    to_vote(table)

    table.vote(dict.fromkeys("acdfg", "b"))

    assert table.of_type("powers_lost")[0].data == {"elder": "b"}
    assert [s.kind for s in table.state.queue] == ["wolf"]  # the Seer no longer acts
    assert table.plugin.get_observation(table.state, "c")["village_powers_lost"] is True
    wolves_take(table, "d")
    assert table.turn != ["d"]  # the Hunter dies without a shot


# --- Village Idiot -----------------------------------------------------------------


IDIOT = {
    "a": "werewolf",
    "b": "village_idiot",
    "c": "villager",
    "d": "villager",
    "e": "villager",
    "f": "villager",
}


def test_an_executed_idiot_survives_revealed_and_loses_the_vote():
    table = Table(IDIOT)
    wolves_take(table, "c")
    to_vote(table)

    table.vote(dict.fromkeys("adef", "b"))

    assert "b" in table.state.alive
    assert table.of_type("idiot_revealed")[0].data == {"player": "b", "role": "village_idiot"}
    wolves_take(table, "d")
    voters = [s.player for s in table.state.queue if s.kind == "vote"]
    assert "b" not in voters
    assert table.plugin.get_observation(table.state, "b")["may_vote"] is False


# --- Scapegoat ----------------------------------------------------------------------


GOAT = {
    "a": "werewolf",
    "b": "scapegoat",
    "c": "villager",
    "d": "villager",
    "e": "villager",
    "f": "villager",
}


def test_a_tied_vote_kills_the_scapegoat():
    table = Table(GOAT)
    wolves_take(table, "f")
    to_vote(table)

    table.vote({"a": "c", "c": "d", "d": "c", "e": "d"})

    assert table.of_type("vote_result")[0].data["executed"] == "b"
    assert deaths(table)[-1] == ("b", "scapegoat")


def test_without_a_tie_the_scapegoat_is_safe():
    table = Table(GOAT)
    wolves_take(table, "f")
    to_vote(table)

    table.vote({"a": "c", "c": "d", "d": "c"})

    assert table.of_type("vote_result")[0].data["executed"] == "c"


@pytest.mark.parametrize("template", ["classic", "duesterwald", "chaos"])
def test_every_template_is_playable(template):
    from games.werewolf.plugin import Werewolf

    state = Werewolf().initial_state([f"p{i}" for i in range(16)], {"template": template})

    assert sum(state.selection.values()) == 16
