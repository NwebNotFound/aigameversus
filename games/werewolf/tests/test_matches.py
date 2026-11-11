"""Whole Werewolf matches with every role: hidden information, replay, bots and the mock LLM."""

import json
import random
import re

import pytest

from arena.agents.mock_llm import MockLLM, tool_call
from arena.agents.random_bot import RandomBot
from arena.agents.runner import ModelAgent
from arena.engine.match import Match
from arena.engine.replay import replay
from arena.engine.rng import derive_rng
from arena.engine.types import MESSAGE, EventSource, TurnRequest
from games.werewolf.plugin import Werewolf
from games.werewolf.selection import load_roles
from games.werewolf.tests.test_plugin import bot_match, run_match

ALL_ROLES = {"roles": dict.fromkeys(load_roles(), 1)}  # every role once: 16 players
PLAYERS_16 = [f"p{i}" for i in range(16)]


# --- who may see a private event ------------------------------------------------


def allowed_audience(event, state):
    """The players who may see this private event, from the rules (not from the plugin)."""
    data = event.data
    actor_only = {
        "role_assigned",
        "seer_inspected",
        "witch_acted",
        "lovers_linked",
        "protected",
        "spied",
        "elder_survived",
        "raven_chose",
        "model_chosen",
        "white_wolf_chose",
    }
    if event.type in actor_only:
        return {data["player"]}
    if event.type == "love_revealed":
        return set(data["lovers"])
    if event.type in ("infected", "joined_pack"):
        return set(state.pack)  # the final pack includes the new member
    if event.type in ("pack_revealed", "wolf_vote", "wolf_talked", "infection_chosen"):
        return set(state.pack)
    if event.type in ("lover_talked",):
        return set(state.lovers)
    if event.type == MESSAGE:
        return set(state.pack) | set(state.lovers)
    return set()  # anything else private is for spectators only


class Spy:
    def __init__(self, plugin, rng):
        self.bot = RandomBot(plugin, rng)
        self.requests: list[TurnRequest] = []

    async def act(self, request):
        self.requests.append(request)
        return await self.bot.act(request)


@pytest.mark.parametrize(
    ("settings", "seed"),
    [(ALL_ROLES, 1), (ALL_ROLES, 2), (ALL_ROLES, 3), ({"template": "chaos"}, 4)],
)
def test_private_events_reach_only_the_players_who_may_know(settings, seed):
    plugin = Werewolf()
    spies = {p: Spy(plugin, derive_rng(seed, "spy", p)) for p in PLAYERS_16}
    match = Match(plugin, spies, seed=seed, settings=settings)
    run_match(match)
    state = match.state

    private = [e for e in match.events if e.source is EventSource.GAME and e.visible_to]
    assert private
    for event in private:
        assert set(event.visible_to) <= allowed_audience(event, state), event

    for player, spy in spies.items():
        for request in spy.requests:
            dead = {d["player"] for d in request.observation["dead"]}
            known = {player} | dead | set(request.observation.get("seer_results", {}))
            text = repr(request.observation)
            for other, role in state.roles.items():
                if other not in known and role != "villager":
                    assert f"'{other}': '{role}'" not in text, (player, other)
            if player not in state.pack:
                assert "pack" not in request.observation


# --- determinism and replay with every role ------------------------------------


def test_same_seed_same_match_with_every_role():
    first, a = bot_match(16, seed=8, settings=ALL_ROLES)
    second, b = bot_match(16, seed=8, settings=ALL_ROLES)

    assert first.events == second.events and a == b


@pytest.mark.parametrize("seed", [9, 10, 11])
def test_replay_rebuilds_a_match_with_every_role(seed):
    match, _ = bot_match(16, seed=seed, settings=ALL_ROLES)

    assert replay(Werewolf(), match.events) == match.state


def test_200_random_bot_matches_over_every_template():
    rng = random.Random(2)
    roles_seen, winners = set(), set()
    for number in range(200):
        template = rng.choice(["classic", "duesterwald", "chaos", "random_balanced", "all"])
        low = {"duesterwald": 8, "chaos": 14, "all": 16}.get(template, 6)
        count = 16 if template == "all" else rng.randint(low, 16)
        settings = ALL_ROLES if template == "all" else {"template": template}
        settings = settings | {"captain": rng.random() < 0.7}
        match, placements = bot_match(count, seed=1000 + number, settings=settings)

        assert match.state.phase == "over", (number, template)
        assert sorted(p.player for p in placements) == sorted(match.state.players)
        roles_seen |= set(match.state.roles.values())
        winners.add(match.state.winner)
    assert roles_seen == set(load_roles())
    assert {"village", "wolves"} <= winners


# --- a mock-LLM match with every role ------------------------------------------


def situation(messages):
    block = re.search(r"<situation>\n(.*)\n</situation>", messages[1]["content"]).group(1)
    return json.loads(block)


def plays_by_the_rules(messages, tools):
    """A model that reads its situation and tools: talks once if it can, then acts.

    It always picks the first allowed choice that is not itself, so the village
    keeps voting the same player and the match ends.
    """
    seen = situation(messages)
    me = seen["you"]
    by_name = {t["function"]["name"]: t["function"] for t in tools}
    for chat in ("lover_chat", "wolf_chat"):
        if chat in by_name:
            return tool_call(chat, {"text": f"{me} here, stay calm."}, text="coordinate first")
    name = next(n for n in by_name if n not in ("lover_chat", "wolf_chat"))
    arguments = {}
    for field, schema in by_name[name]["parameters"]["properties"].items():
        if "enum" in schema:
            taken = (me, None, *arguments.values())
            options = [o for o in schema["enum"] if o not in taken] or schema["enum"]
            arguments[field] = options[0]
        elif field in by_name[name]["parameters"].get("required", []):
            arguments[field] = f"I am {me} and I am harmless."
    return tool_call(name, arguments, text=f"secret plan of {me}")


async def no_pause(seconds):
    pass


def test_mock_llm_seats_play_a_whole_match_with_every_role():
    plugin = Werewolf()
    # Every seat's first answer names a player who does not exist, to exercise the correction.
    bad = tool_call("vote", {"target": "nobody-here"})
    mocks = {p: MockLLM(bad, plays_by_the_rules) for p in PLAYERS_16}
    agents = {p: ModelAgent(m, plugin, sleep=no_pause) for p, m in mocks.items()}
    match = Match(plugin, agents, seed=12, settings=ALL_ROLES | {"language": "en"})

    run_match(match)

    state = match.state
    assert state.phase == "over" and state.winner is not None
    assert any(e.type == "action_rejected" for e in match.events)  # the bad first answers
    used = {e.data.get("tool") for e in match.events if e.type == "action_accepted"}
    assert {"wolf_kill", "seer_check", "witch_act", "link_lovers", "speak", "vote"} <= used
    for mock in mocks.values():
        for messages, _ in mock.calls:
            assert "secret plan of" not in json.dumps(messages)  # thoughts never reach prompts
    lines = [e.data["text"] for e in match.events if e.type == "narration"]
    assert lines[0] == "Night 1 falls. The village sleeps." and len(lines) > 3
    assert replay(Werewolf(), match.events) == state
