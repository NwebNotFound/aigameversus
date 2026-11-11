"""Roles batch B: Raven, Wild Child, Prime Wolf, White Werewolf, Bear Tamer."""

from games.werewolf.tests.test_plugin import Table


def deaths(table):
    return [(e.data["player"], e.data["cause"]) for e in table.of_type("player_died")]


def keys(table):
    return [e.data["key"] for e in table.of_type("narration")]


# --- Raven ---------------------------------------------------------------------


RAVEN = {
    "a": "werewolf",
    "b": "raven",
    "c": "villager",
    "d": "villager",
    "e": "villager",
    "f": "villager",
    "g": "villager",
}


def test_the_raven_mark_is_announced_and_adds_two_votes():
    table = Table(RAVEN)
    table.act("a", "wolf_kill", target="g")
    table.act("b", "mark", target="c")

    assert table.of_type("raven_chose")[0].visible_to == ("b",)
    announced = table.of_type("raven_mark_announced")[0]
    assert announced.data == {"target": "c"} and announced.visible_to is None
    assert "raven_mark" in keys(table)
    assert table.plugin.get_observation(table.state, "d")["raven_mark"] == "c"
    table.talk_through_day()

    # 2 votes for d, 1 for c: with the mark c has 3 and is executed.
    table.vote({"a": "d", "b": "c", "e": "d"})

    assert table.of_type("vote_result")[0].data["counts"] == {"d": 2, "c": 3}
    assert table.of_type("vote_result")[0].data["executed"] == "c"
    assert table.state.marked is None


def test_no_mark_when_the_raven_passes_or_the_marked_dies():
    table = Table(RAVEN)
    table.act("a", "wolf_kill", target="c")

    table.act("b", "mark", target="c")  # c dies tonight

    assert table.of_type("raven_mark_announced") == []
    table.talk_through_day()
    table.vote({})
    table.act("a", "wolf_kill", target="d")
    table.act("b", "mark", target=None)
    assert table.of_type("raven_chose")[-1].data["target"] == "c"  # no new mark
    assert len(table.of_type("raven_mark_announced")) == 0


# --- Wild Child --------------------------------------------------------------------


CHILD = {
    "a": "werewolf",
    "b": "wild_child",
    "c": "villager",
    "d": "villager",
    "e": "villager",
    "f": "villager",
    "g": "villager",
}


def test_wild_child_joins_the_pack_when_the_model_dies():
    table = Table(CHILD)
    assert [s.player for s in table.state.queue] == ["b", "a"]  # wild child: night order 2

    table.act("b", "choose_model", target="c")
    assert table.of_type("model_chosen")[0].visible_to == ("b",)
    assert table.plugin.get_observation(table.state, "b")["role_model"] == "c"
    table.act("a", "wolf_kill", target="c")

    joined = table.of_type("joined_pack")[0]
    assert joined.data == {"player": "b"} and set(joined.visible_to) == {"a", "b"}
    assert "b" in table.state.pack
    table.talk_through_day()
    table.vote({})
    assert [(s.kind, s.player) for s in table.state.queue] == [("wolf", "a"), ("wolf", "b")]


def test_wild_child_stays_with_the_village_while_the_model_lives():
    table = Table(CHILD)
    table.act("b", "choose_model", target="c")

    table.act("a", "wolf_kill", target="d")

    assert table.of_type("joined_pack") == [] and "b" not in table.state.pack


# --- Prime Wolf -----------------------------------------------------------------------


PRIME = {
    "a": "werewolf",
    "b": "prime_wolf",
    "c": "witch",
    "d": "villager",
    "e": "villager",
    "f": "villager",
    "g": "villager",
}


def test_prime_wolf_infects_the_victim_once():
    table = Table(PRIME)
    assert [(s.kind, s.player) for s in table.state.queue] == [
        ("wolf", "a"),
        ("wolf", "b"),
        ("night", "b"),  # infection decision after the votes
        ("night", "c"),
    ]
    table.act("a", "wolf_kill", target="d")
    table.act("b", "wolf_kill", target="d")
    assert set(table.tools("b")) == {"infect", "let_them_die"}

    table.act("b", "infect")
    table.act("c", "witch_act", heal=False, poison_target=None)

    assert deaths(table) == []
    infected = table.of_type("infected")[0]
    assert infected.data == {"player": "d"} and set(infected.visible_to) == {"a", "b", "d"}
    assert "d" in table.state.pack
    assert table.plugin.get_observation(table.state, "b")["infection_used"] is True
    table.talk_through_day()
    table.vote({})
    assert ("night", "b") not in [(s.kind, s.player) for s in table.state.queue]


def test_infecting_a_healed_victim_does_nothing():
    table = Table(PRIME)
    table.act("a", "wolf_kill", target="d")
    table.act("b", "wolf_kill", target="d")
    table.act("b", "infect")

    table.act("c", "witch_act", heal=True, poison_target=None)

    assert table.of_type("infected") == [] and "d" not in table.state.pack
    assert table.state.infection_used


def test_letting_the_victim_die():
    table = Table(PRIME)
    table.act("a", "wolf_kill", target="d")
    table.act("b", "wolf_kill", target="d")
    table.act("b", "let_them_die")

    table.act("c", "witch_act", heal=False, poison_target=None)

    assert deaths(table) == [("d", "wolves")] and not table.state.infection_used


# --- White Werewolf ------------------------------------------------------------------


WHITE = {
    "a": "werewolf",
    "b": "white_wolf",
    "c": "villager",
    "d": "villager",
    "e": "villager",
    "f": "villager",
    "g": "villager",
}


def night(table, victim, white=None):
    table.act("a", "wolf_kill", target=victim) if "a" in table.state.alive else None
    table.act("b", "wolf_kill", target=victim)
    if table.state.queue and table.state.queue[0].kind == "night":
        table.act("b", "white_wolf_kill", target=white)


def test_white_wolf_acts_every_second_night_and_kills_a_wolf():
    table = Table(WHITE)
    assert ("night", "b") not in [(s.kind, s.player) for s in table.state.queue]  # night 1
    night(table, "c")
    table.talk_through_day()
    table.vote({})

    assert [s.kind for s in table.state.queue][-1] == "night"  # night 2: white wolf at slot 7
    table.act("a", "wolf_kill", target="d")
    table.act("b", "wolf_kill", target="d")
    assert table.tools("b")["white_wolf_kill"].parameters["properties"]["target"]["enum"] == [
        None,
        "a",
    ]
    table.act("b", "white_wolf_kill", target="a")

    assert sorted(deaths(table)) == [("a", "white_wolf"), ("c", "wolves"), ("d", "wolves")]
    assert table.of_type("white_wolf_chose")[0].visible_to == ("b",)


def test_white_wolf_wins_only_as_the_last_alive():
    roles = {
        "a": "werewolf",
        "b": "white_wolf",
        "c": "villager",
        "d": "villager",
        "e": "villager",
        "f": "villager",
    }
    table = Table(roles)
    table.state.alive = ["b", "c"]
    table.state.phase = "dusk"
    table.state.queue = []

    table.plugin.step(table.state, table.ctx())
    assert table.of_type("game_over") == []  # b and c alive: nobody has won

    table.state.alive = ["b"]
    table.state.phase = "dusk"
    table.state.queue = []
    table.plugin.step(table.state, table.ctx())
    assert table.of_type("game_over")[0].data == {"winner": "white_wolf", "winners": ["b"]}


def test_the_pack_wins_without_the_white_wolf():
    table = Table(WHITE)
    table.state.alive = ["a", "b", "c"]
    table.state.phase = "dusk"
    table.state.queue = []

    table.plugin.step(table.state, table.ctx())  # a (wolf) vs b, c: no win yet
    assert table.of_type("game_over") == []
    table.state.alive = ["a", "c"]
    table.state.phase = "dusk"
    table.state.queue = []
    table.plugin.step(table.state, table.ctx())

    assert table.of_type("game_over")[0].data == {"winner": "wolves", "winners": ["a"]}


# --- Bear Tamer ------------------------------------------------------------------


def test_the_bear_growls_next_to_a_living_wolf():
    table = Table(
        {
            "t": "bear_tamer",
            "w": "werewolf",
            "c": "villager",
            "d": "villager",
            "e": "villager",
            "f": "villager",
        }
    )

    table.act("w", "wolf_kill", target="d")

    assert table.of_type("bear_growled")[0].visible_to is None
    assert "bear_growl" in keys(table)


def test_the_bear_is_quiet_without_a_wolf_beside_and_skips_the_dead():
    # Seats: t, c, d, w, e, f in a circle; t's neighbours are c and f.
    roles = {
        "t": "bear_tamer",
        "c": "villager",
        "d": "villager",
        "w": "werewolf",
        "e": "villager",
        "f": "villager",
    }
    table = Table(roles)
    table.act("w", "wolf_kill", target="d")
    assert table.of_type("bear_growled") == []
    table.talk_through_day()
    table.vote(
        {p: "c" for p in "tefw"}
    )  # c executed: now t sits next to ... f and (skipping c, d) w

    table.act("w", "wolf_kill", target="e")

    assert len(table.of_type("bear_growled")) == 1
