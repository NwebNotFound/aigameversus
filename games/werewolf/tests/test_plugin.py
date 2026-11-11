import asyncio
import random

import pytest

from arena.agents.random_bot import RandomBot, random_bots
from arena.engine.match import Match
from arena.engine.plugin import TurnContext
from arena.engine.replay import replay
from arena.engine.rng import derive_rng
from arena.engine.types import MESSAGE, Action, Event, EventSource, TurnRequest
from games.werewolf.plugin import Werewolf

MATCH_TIME_LIMIT = 10  # seconds; a rule that never ends a match fails fast


# --- helpers -------------------------------------------------------------------


class Table:
    """A match from hand-made role events: `roles` maps players (seat order) to role ids."""

    def __init__(self, roles, *, speaking_start=0, captain=False, language="en", seed=0):
        self.plugin = Werewolf()
        settings = {"roles": _counts(roles), "captain": captain, "language": language}
        self.state = self.plugin.initial_state(list(roles), settings)
        self.events: list[Event] = []
        self.speaking_start = speaking_start
        self.seed = seed
        for player, role in roles.items():
            self.apply("role_assigned", player=player, role=role)
        pack = [p for p, r in roles.items() if r == "werewolf"]
        self.apply("pack_revealed", wolves=pack)
        self.apply("night_started", night=1)

    def apply(self, type, **data):
        self.plugin.apply_event(self.state, Event(source=EventSource.GAME, type=type, data=data))

    def ctx(self):
        start = self.speaking_start

        class Fixed(random.Random):
            def randrange(self, n):
                return start % n

        def record(event):
            self.plugin.apply_event(self.state, event)
            self.events.append(event)

        return TurnContext(lambda *key: Fixed(f"{self.seed}{key!r}"), record)

    @property
    def turn(self):
        return self.plugin.active_players(self.state)

    def act(self, player, tool, **arguments):
        assert self.turn == [player], (self.turn, player)
        action = Action(tool=tool, arguments=arguments)
        names = {t.name for t in self.plugin.get_tools(self.state, player)}
        assert tool in names, (tool, names)
        problem = self.plugin.validate(self.state, player, action)
        assert problem is None, problem
        self.plugin.apply_actions(self.state, {player: action}, self.ctx())

    def tools(self, player):
        return {t.name: t for t in self.plugin.get_tools(self.state, player)}

    def of_type(self, type):
        return [e for e in self.events if e.type == type]

    def talk_through_day(self):
        """Every speech of the day, then nothing else."""
        while self.state.queue and self.state.queue[0].kind == "speak":
            self.act(self.turn[0], "speak", text="Hm.")

    def vote(self, votes):
        """Votes in queue order; `votes` maps voter to target (None abstains)."""
        while self.state.queue and self.state.queue[0].kind == "vote":
            voter = self.turn[0]
            self.act(voter, "vote", target=votes.get(voter))


def _counts(roles):
    counts = {}
    for role in roles.values():
        counts[role] = counts.get(role, 0) + 1
    return counts


CLASSIC = {
    "a": "werewolf",
    "b": "seer",
    "c": "witch",
    "d": "hunter",
    "e": "werewolf",
    "f": "villager",
    "g": "villager",
    "h": "villager",
}


def run_match(match):
    async def bounded():
        try:
            async with asyncio.timeout(MATCH_TIME_LIMIT):
                return await match.run()
        except TimeoutError:
            pytest.fail(f"match did not end within {MATCH_TIME_LIMIT} s")

    return asyncio.run(bounded())


def bot_match(count, *, seed=1, settings=None, agents=None):
    plugin = Werewolf()
    players = [f"p{i}" for i in range(count)]
    bots = random_bots(plugin, players, seed) | (agents or {})
    match = Match(plugin, bots, seed=seed, settings=settings or {})
    return match, run_match(match)


# --- settings ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"moon": "full"}, "Unknown settings"),
        ({"template": "classic", "roles": {"werewolf": 1}}, "either a template or roles"),
        ({"roles": {"seer": 2, "werewolf": 1}}, "Seherin may appear only once"),
        ({"roles": {"werewolf": 2, "bear_tamer": 1}}, "Roles not playable yet: bear_tamer"),
    ],
)
def test_bad_settings_are_rejected(settings, message):
    with pytest.raises(ValueError, match=message):
        Werewolf().initial_state([f"p{i}" for i in range(8)], settings)


def test_default_is_the_classic_template():
    state = Werewolf().initial_state([f"p{i}" for i in range(8)], {})

    assert state.selection == {"werewolf": 2, "seer": 1, "witch": 1, "hunter": 1, "villager": 3}


# --- setup -------------------------------------------------------------------------


def test_roles_are_private_and_the_pack_knows_itself():
    match, _ = bot_match(8, seed=3)
    events = [e for e in match.events if e.source is EventSource.GAME]

    assigned = [e for e in events if e.type == "role_assigned"]
    assert all(e.visible_to == (e.data["player"],) for e in assigned)
    pack = next(e for e in events if e.type == "pack_revealed")
    wolves = [e.data["player"] for e in assigned if e.data["role"] == "werewolf"]
    assert pack.data["wolves"] == wolves and pack.visible_to == tuple(wolves)
    assert next(e for e in events if e.type == "roles_dealt").visible_to == ()


def test_public_role_list_when_enabled():
    match, _ = bot_match(8, seed=3, settings={"roles_public": True})

    listed = next(e for e in match.events if e.type == "roles_in_play")
    assert listed.visible_to is None
    assert listed.data["selection"]["werewolf"] == 2


# --- night order ------------------------------------------------------------------


def test_night_follows_the_role_files_order():
    table = Table(CLASSIC)

    assert [(s.kind, s.player) for s in table.state.queue] == [
        ("night", "b"),  # seer: 4
        ("wolf", "a"),  # wolves: 6, seat order
        ("wolf", "e"),
        ("night", "c"),  # witch: 8
    ]


def test_seer_learns_a_role_privately():
    table = Table(CLASSIC)

    table.act("b", "seer_check", target="e")

    seen = table.of_type("seer_inspected")[0]
    assert seen.data == {"player": "b", "target": "e", "role": "werewolf"}
    assert seen.visible_to == ("b",)
    assert table.plugin.get_observation(table.state, "b")["seer_results"] == {"e": "werewolf"}
    assert "seer_results" not in table.plugin.get_observation(table.state, "a")


def test_wolves_chat_privately_at_most_twice_then_vote():
    table = Table(CLASSIC)
    table.act("b", "seer_check", target="f")

    table.act("a", "wolf_chat", text="Take the seer?")
    table.act("a", "wolf_chat", text="Or the witch.")
    assert "wolf_chat" not in table.tools("a")
    table.act("a", "wolf_kill", target="c")

    chats = [e for e in table.of_type(MESSAGE)]
    assert [e.data["text"] for e in chats] == ["Take the seer?", "Or the witch."]
    assert all(e.visible_to == ("a", "e") for e in chats)
    assert table.of_type("wolf_vote")[0].visible_to == ("a", "e")
    assert set(table.tools("e")["wolf_kill"].parameters["properties"]["target"]["enum"]) == set(
        "bcdfgh"
    )


def test_wolf_majority_and_tie_rule():
    table = Table(CLASSIC)
    table.act("b", "seer_check", target="f")
    # Tie 1:1. The first vote (a) is for g, the later one (e) for f: g wins,
    # although f comes first by name and by seat.
    table.act("a", "wolf_kill", target="g")
    table.act("e", "wolf_kill", target="f")

    assert table.state.wolf_victim() == "g"


def test_witch_sees_the_victim_only_on_her_turn_and_can_heal():
    table = Table(CLASSIC)
    table.act("b", "seer_check", target="f")
    table.act("a", "wolf_kill", target="f")
    assert "wolf_victim" not in table.plugin.get_observation(table.state, "c")
    table.act("e", "wolf_kill", target="f")

    assert table.plugin.get_observation(table.state, "c")["wolf_victim"] == "f"
    table.act("c", "witch_act", heal=True, poison_target=None)

    assert table.of_type("morning_started")[0].data == {"night": 1, "deaths": []}
    assert "f" in table.state.alive
    assert table.state.potions == {"heal": False, "poison": True}


def test_witch_poison_kills_and_each_potion_works_once():
    table = Table(CLASSIC)
    table.act("b", "seer_check", target="f")
    table.act("a", "wolf_kill", target="f")
    table.act("e", "wolf_kill", target="f")

    table.act("c", "witch_act", heal=True, poison_target="a")

    assert [e.data["player"] for e in table.of_type("player_died")] == ["a"]
    assert table.of_type("player_died")[0].data["cause"] == "poison"
    table.talk_through_day()
    table.vote({})
    table.act("b", "seer_check", target="g")
    table.act("e", "wolf_kill", target="g")
    witch = table.tools("c")["witch_act"].parameters["properties"]
    assert witch["heal"]["enum"] == [False]
    assert witch["poison_target"]["enum"] == [None]


def test_unhealed_victim_dies_and_reveals_the_role():
    table = Table(CLASSIC)
    table.act("b", "seer_check", target="f")
    table.act("a", "wolf_kill", target="b")
    table.act("e", "wolf_kill", target="b")
    table.act("c", "witch_act", heal=False, poison_target=None)

    died = table.of_type("player_died")[0]
    assert died.data == {"player": "b", "cause": "wolves", "role": "seer"}
    assert died.visible_to is None
    assert {"player": "b", "role": "seer"} in table.plugin.get_observation(table.state, "f")["dead"]


# --- hunter -----------------------------------------------------------------------


def test_hunter_killed_at_night_shoots_before_the_day():
    table = Table(CLASSIC)
    table.act("b", "seer_check", target="f")
    table.act("a", "wolf_kill", target="d")
    table.act("e", "wolf_kill", target="d")
    table.act("c", "witch_act", heal=False, poison_target=None)

    assert table.turn == ["d"] and set(table.tools("d")) == {"hunter_shoot"}
    table.act("d", "hunter_shoot", target="a")

    assert [(e.data["player"], e.data["cause"]) for e in table.of_type("player_died")] == [
        ("d", "wolves"),
        ("a", "hunter"),
    ]
    assert table.state.phase == "day"


def test_executed_hunter_shoots_at_dusk():
    table = Table(CLASSIC)
    table.act("b", "seer_check", target="f")
    table.act("a", "wolf_kill", target="f")
    table.act("e", "wolf_kill", target="f")
    table.act("c", "witch_act", heal=True, poison_target=None)
    table.talk_through_day()

    table.vote({p: "d" for p in "abcefgh"})

    assert table.of_type("vote_result")[0].data["executed"] == "d"
    assert table.turn == ["d"]
    table.act("d", "hunter_shoot", target="e")
    assert table.state.night == 2


# --- day ------------------------------------------------------------------------


def test_discussion_is_two_rounds_from_a_seeded_start():
    table = Table(CLASSIC, speaking_start=3)
    table.act("b", "seer_check", target="f")
    table.act("a", "wolf_kill", target="f")
    table.act("e", "wolf_kill", target="f")
    table.act("c", "witch_act", heal=False, poison_target=None)

    order = ["d", "e", "g", "h", "a", "b", "c"]  # f died; start at index 3 of the living
    assert table.state.speaking_order == order
    assert [s.player for s in table.state.queue if s.kind == "speak"] == order * 2


def test_speech_word_limit():
    table = Table(CLASSIC)
    table.act("b", "seer_check", target="f")
    table.act("a", "wolf_kill", target="f")
    table.act("e", "wolf_kill", target="f")
    table.act("c", "witch_act", heal=True, poison_target=None)
    speaker = table.turn[0]

    problem = table.plugin.validate(
        table.state, speaker, Action(tool="speak", arguments={"text": " ".join(["w"] * 121)})
    )

    assert problem == "Your text has 121 words; say it in at most 120."


def _to_vote(table):
    table.act("b", "seer_check", target="f")
    table.act("a", "wolf_kill", target="f")
    table.act("e", "wolf_kill", target="f")
    table.act("c", "witch_act", heal=True, poison_target=None)
    table.talk_through_day()


def test_most_votes_are_executed_and_abstentions_do_not_count():
    table = Table(CLASSIC)
    _to_vote(table)

    table.vote({"a": "f", "b": "e", "c": "e", "d": "e", "e": "f", "f": None, "g": None, "h": "e"})

    assert table.of_type("vote_result")[0].data == {
        "day": 1,
        "counts": {"f": 2, "e": 4},
        "executed": "e",
    }


def test_a_tie_executes_nobody():
    table = Table(CLASSIC)
    _to_vote(table)

    table.vote({"a": "f", "b": "e", "e": "f", "c": "e"})

    assert table.of_type("vote_result")[0].data["executed"] is None
    assert table.state.night == 2


def test_vote_reason_is_a_public_message():
    table = Table(CLASSIC)
    _to_vote(table)
    voter = table.turn[0]

    table.act(voter, "vote", target="e", reason="Too quiet.")

    assert {"player": voter, "text": "Too quiet."} in [e.data for e in table.of_type(MESSAGE)]


# --- winning ------------------------------------------------------------------------


def test_village_wins_when_the_last_wolf_dies():
    table = Table(
        {
            "a": "werewolf",
            "b": "seer",
            "c": "witch",
            "d": "villager",
            "e": "villager",
            "f": "villager",
        }
    )
    table.act("b", "seer_check", target="a")
    table.act("a", "wolf_kill", target="d")
    table.act("c", "witch_act", heal=False, poison_target="a")

    assert table.of_type("game_over")[0].data == {
        "winner": "village",
        "winners": ["b", "c", "d", "e", "f"],
    }
    ranks = {(p.player, p.rank) for p in table.plugin.results(table.state)}
    assert ("a", 6) in ranks and ("b", 1) in ranks


def test_wolves_win_at_parity():
    roles = {
        "a": "werewolf",
        "b": "werewolf",
        "c": "seer",
        "d": "villager",
        "e": "villager",
        "f": "villager",
    }
    table = Table(roles)
    table.act("c", "seer_check", target="a")
    table.act("a", "wolf_kill", target="d")
    table.act("b", "wolf_kill", target="d")  # 2 wolves vs c, e, f
    table.talk_through_day()
    table.vote({"a": "c", "b": "c", "e": "c"})  # c executed: 2 wolves vs e, f

    assert table.of_type("game_over")[0].data["winner"] == "wolves"
    assert table.state.phase == "over" and table.turn == []


# --- whole matches -------------------------------------------------------------------


class Spy:
    def __init__(self, plugin, rng):
        self.bot = RandomBot(plugin, rng)
        self.requests: list[TurnRequest] = []

    async def act(self, request):
        self.requests.append(request)
        return await self.bot.act(request)


# Game events a player may ever receive in public. Anything else must stay private.
PUBLIC_EVENTS = {
    MESSAGE,
    "roles_in_play",
    "night_started",
    "morning_started",
    "player_died",
    "hunter_shot",
    "day_started",
    "vote_cast",
    "vote_result",
    "game_over",
    "narration",
    "captain_vote",
    "captain_elected",
    "captain_passed",
}
# Game events that may reach a player privately (their audience is checked below).
PRIVATE_EVENTS = {
    MESSAGE,  # wolf chat, to the pack only
    "role_assigned",
    "pack_revealed",
    "wolf_vote",
    "wolf_talked",
    "seer_inspected",
    "witch_acted",
}


def test_a_hunter_dying_last_gets_no_shot():
    table = Table(CLASSIC)
    table.state.alive = ["d"]

    table.apply("player_died", player="d", cause="wolves", role="hunter")

    assert all(step.kind != "hunter" for step in table.state.queue)


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_no_player_learns_a_hidden_role(seed):
    plugin = Werewolf()
    players = [f"p{i}" for i in range(10)]
    spies = {p: Spy(plugin, derive_rng(seed, "spy", p)) for p in players}
    match = Match(plugin, spies, seed=seed, settings={"template": "random_balanced"})
    run_match(match)
    roles = match.state.roles
    pack = match.state.pack

    for player, spy in spies.items():
        for request in spy.requests:
            dead = {d["player"] for d in request.observation["dead"]}
            for event in request.events:
                if event.source is EventSource.GAME:
                    allowed = PUBLIC_EVENTS if event.visible_to is None else PRIVATE_EVENTS
                    assert event.type in allowed, (player, event.type, event.visible_to)
                if event.type == "role_assigned":
                    assert event.data["player"] == player
                if event.type in ("pack_revealed", "wolf_vote", "wolf_talked"):
                    assert player in pack
                if event.type == "seer_inspected":
                    assert event.data["player"] == player
                assert event.type not in ("roles_dealt",)
            if player not in pack:
                assert "pack" not in request.observation
            known = {player} | dead | set(request.observation.get("seer_results", {}))
            if player in pack:
                known |= set(pack)
            text = repr(request.observation)
            for other, role in roles.items():
                if other not in known and role not in ("villager",):
                    assert f"'{other}': '{role}'" not in text


def test_same_seed_same_match():
    first, a = bot_match(9, seed=5)
    second, b = bot_match(9, seed=5)
    other, _ = bot_match(9, seed=6)

    assert first.events == second.events and a == b
    assert first.events != other.events


def test_replay_rebuilds_the_end_state():
    match, _ = bot_match(12, seed=7, settings={"template": "random_balanced"})

    assert replay(Werewolf(), match.events) == match.state


def test_200_random_bot_matches_end_with_a_winner():
    rng = random.Random(1)
    winners = set()
    for number in range(200):
        count = rng.randint(6, 16)
        template = rng.choice(["classic", "random_balanced"])
        match, placements = bot_match(count, seed=number, settings={"template": template})

        assert match.state.phase == "over", number
        assert match.state.winner in ("village", "wolves", "lovers", "nobody")
        assert sorted(p.player for p in placements) == sorted(match.state.players)
        winners.add(match.state.winner)
    assert {"village", "wolves"} <= winners


def test_render_spec_shows_every_role_to_spectators():
    table = Table(CLASSIC)

    spec = table.plugin.render_spec(table.state)

    assert spec["layout"] == "player_circle"
    assert [s["role"] for s in spec["seats"]] == list(CLASSIC.values())
