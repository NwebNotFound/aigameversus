"""Cost caps, against a real ledger in Postgres. The models are mocks: nothing here costs money."""

import asyncio
import json
import logging
import re
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from functools import partial
from uuid import uuid4

import pytest

from arena.agents.budget import Budget
from arena.agents.mock_llm import HANGS, MockLLM, tool_call
from arena.agents.model import ModelError, ModelReply, Usage
from arena.agents.runner import ModelAgent
from arena.config import Config, Limits, Model
from arena.db.database import connect, migrate
from arena.db.event_store import EventStore
from arena.db.ledger import Ledger
from arena.engine.match import Match
from arena.engine.replay import replay
from arena.engine.types import EventSource, MatchPaused
from games.toy.plugin import ToyGame

PLAYERS = ["p1", "p2", "p3"]
CALLS_PER_MATCH = 9  # three players, three tricks
MESSAGES = [{"role": "user", "content": "It is your turn."}]
TOOLS = []
INPUT_BOUND = len(json.dumps([MESSAGES, TOOLS]))  # no prompt has more tokens than bytes
MAX_OUTPUT = 100
NOVEMBER = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
PLAY_3 = tool_call("play_card", {"card": 3}, usage=Usage(input_tokens=120, output_tokens=30))


def config(*, usd_to_eur="1", max_input_tokens=5000):
    return Config(
        limits=Limits(
            match_eur=Decimal("0.01"),
            month_eur=Decimal("0.05"),
            usd_to_eur=Decimal(usd_to_eur),
            max_input_tokens=max_input_tokens,
            max_output_tokens=MAX_OUTPUT,
        ),
        models={
            # One and two millionths of a euro per token: easy to count.
            "cheap": Model(
                provider="openrouter",
                model="some-vendor/cheap-model",
                input_usd_per_mtok=Decimal("1"),
                output_usd_per_mtok=Decimal("2"),
            ),
            "odd": Model(
                provider="openrouter",
                model="some-vendor/odd-model",
                input_usd_per_mtok=Decimal("0.051"),
                output_usd_per_mtok=Decimal("0.567"),
            ),
            # Like "cheap", but it may answer at length.
            "long": Model(
                provider="openrouter",
                model="some-vendor/long-model",
                input_usd_per_mtok=Decimal("1"),
                output_usd_per_mtok=Decimal("2"),
                max_output_tokens=4 * MAX_OUTPUT,
            ),
        },
    )


UPPER_BOUND = INPUT_BOUND * 1 + MAX_OUTPUT * 2  # what a call of "cheap" can cost at most


def with_pool(database_url, scenario):
    """Run `scenario(pool)` against a migrated, empty database."""

    async def run():
        pool = await connect(database_url)
        try:
            await migrate(pool)
            return await scenario(pool)
        finally:
            await pool.close()

    return asyncio.run(run())


async def booked(pool):
    """The ledger: one tuple per call, oldest first."""
    rows = await pool.fetch(
        "SELECT match_id, player, model, input_tokens, output_tokens, cost_micro_eur "
        "FROM model_calls ORDER BY id"
    )
    return [tuple(row.values()) for row in rows]


def budget_of(pool, *, match_id=None, now=NOVEMBER, **settings):
    return Budget(Ledger(pool), match_id or uuid4(), config(**settings), now=lambda: now)


async def no_pause(seconds):
    pass


def test_call_is_booked_at_the_tokens_the_provider_counted(database_url):
    match_id = uuid4()

    async def scenario(pool):
        mock = MockLLM(PLAY_3)
        call = budget_of(pool, match_id=match_id).meter("p1", "cheap", mock)
        return await call(MESSAGES, TOOLS), mock.calls, await booked(pool)

    reply, sent, rows = with_pool(database_url, scenario)

    # The model call itself is untouched by the metering.
    assert reply == PLAY_3
    assert sent == [(MESSAGES, TOOLS)]
    assert rows == [(match_id, "p1", "cheap", 120, 30, 120 * 1 + 30 * 2)]


@pytest.mark.parametrize(
    ("model", "usd_to_eur", "usage", "cost"),
    [
        ("odd", "1", Usage(10, 3), 3),  # 0.51 + 1.701 = 2.211 millionths of a dollar
        ("odd", "1", Usage(1, 0), 1),  # even 0.051 counts as a whole millionth
        ("cheap", "0.9", Usage(100, 0), 90),
        ("cheap", "0.9", Usage(101, 0), 91),  # 90.9
        ("cheap", "1", Usage(0, 0), 0),
    ],
)
def test_cost_is_rounded_up_to_a_millionth_of_a_euro(database_url, model, usd_to_eur, usage, cost):
    async def scenario(pool):
        mock = MockLLM(ModelReply(text="hm", usage=usage))
        await budget_of(pool, usd_to_eur=usd_to_eur).meter("p1", model, mock)(MESSAGES, TOOLS)
        return await booked(pool)

    assert [row[-1] for row in with_pool(database_url, scenario)] == [cost]


@pytest.mark.parametrize(
    ("step", "outcome"),
    [
        (ModelReply(text="no usage in this answer"), ModelReply),
        (ModelError("Timeout"), ModelError),  # a rate limit is the exception: booked at 0
        (HANGS, TimeoutError),
    ],
    ids=["answer without usage", "failed call", "call that never answers"],
)
def test_call_that_reports_no_tokens_stays_booked_at_its_upper_bound(database_url, step, outcome):
    async def scenario(pool):
        call = budget_of(pool).meter("p2", "cheap", MockLLM(step))
        try:
            async with asyncio.timeout(0.2):
                result = await call(MESSAGES, TOOLS)
        except (ModelError, TimeoutError) as error:
            result = error
        return result, await booked(pool)

    result, rows = with_pool(database_url, scenario)

    assert isinstance(result, outcome)
    # The provider may have billed the call anyway, so the worst case stays.
    assert [row[1:] for row in rows] == [("p2", "cheap", None, None, UPPER_BOUND)]


def test_call_billed_above_its_upper_bound_is_booked_as_billed(database_url):
    # More input tokens than the request has bytes: no tokenizer does that, but
    # if a provider ever bills it, the ledger must not pretend otherwise.
    greedy = ModelReply(text="hm", usage=Usage(INPUT_BOUND + 1000, MAX_OUTPUT))

    async def scenario(pool):
        budget = budget_of(pool)
        budget.match_cap = UPPER_BOUND + 500
        call = budget.meter("p1", "cheap", MockLLM(greedy))
        await call(MESSAGES, TOOLS)
        with pytest.raises(MatchPaused) as pause:
            await call(MESSAGES, TOOLS)
        return pause.value, await booked(pool)

    pause, rows = with_pool(database_url, scenario)

    # The cap is passed by what the bound was wrong by, once: the next call pauses.
    assert [row[-1] for row in rows] == [UPPER_BOUND + 1000]
    assert pause.data["spent_micro_eur"] == UPPER_BOUND + 1000


def test_call_that_could_pass_the_match_cap_is_not_sent(database_url):
    async def scenario(pool):
        mock = MockLLM(PLAY_3)
        budget = budget_of(pool)
        call = budget.meter("p1", "cheap", mock)
        await call(MESSAGES, TOOLS)  # costs 180
        budget.match_cap = 180 + UPPER_BOUND - 1
        with pytest.raises(MatchPaused) as pause:
            await call(MESSAGES, TOOLS)
        at_pause = len(mock.calls), await booked(pool)
        budget.match_cap += 1  # the user allows more
        await call(MESSAGES, TOOLS)
        return pause.value, at_pause, len(mock.calls), budget.match_cap

    pause, (sent_at_pause, rows_at_pause), sent, cap = with_pool(database_url, scenario)

    assert pause.reason == "match_cap"
    assert pause.data == {
        "player": "p1",
        "spent_micro_eur": 180,
        "cap_micro_eur": cap - 1,
        "call_micro_eur": UPPER_BOUND,
    }
    # The refused call reached no model and left nothing in the ledger.
    assert (sent_at_pause, len(rows_at_pause)) == (1, 1)
    assert sent == 2


def test_caps_come_from_the_config_in_millionths_of_a_euro(database_url):
    async def scenario(pool):
        budget = budget_of(pool)
        return budget.match_cap, budget.month_cap

    assert with_pool(database_url, scenario) == (10_000, 50_000)


def test_month_cap_counts_all_matches_of_the_calendar_month_in_utc(database_url):
    october = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    # Already November in Berlin, still October in UTC.
    last_hour_of_october = datetime(2026, 11, 1, 0, 30, tzinfo=timezone(timedelta(hours=1)))
    first_minute_of_december = datetime(2026, 12, 1, 0, 0, tzinfo=UTC)
    room_for_one = UPPER_BOUND
    not_quite_room_for_a_second = 180 + UPPER_BOUND - 1  # a settled call costs 180

    async def spend(pool, now, *, month_cap):
        """One call of a new match at `now`. Returns the pause, if the month cap stops it."""
        budget = budget_of(pool, now=now)
        budget.month_cap = month_cap
        try:
            await budget.meter("p1", "cheap", MockLLM(PLAY_3))(MESSAGES, TOOLS)
        except MatchPaused as pause:
            return pause

    async def scenario(pool):
        return [
            await spend(pool, october, month_cap=room_for_one),
            await spend(pool, last_hour_of_october, month_cap=not_quite_room_for_a_second),
            await spend(pool, NOVEMBER, month_cap=room_for_one),
            await spend(pool, NOVEMBER + timedelta(days=1), month_cap=not_quite_room_for_a_second),
            await spend(pool, NOVEMBER + timedelta(days=1), month_cap=180 + UPPER_BOUND),
            await spend(pool, first_minute_of_december, month_cap=room_for_one),
        ]

    outcomes = with_pool(database_url, scenario)

    # Another match in the same month is stopped by what the first one spent;
    # a new month starts from zero.
    assert [pause and pause.reason for pause in outcomes] == [
        None,
        "month_cap",
        None,
        "month_cap",
        None,
        None,
    ]
    assert outcomes[3].data == {
        "player": "p1",
        "spent_micro_eur": 180,
        "cap_micro_eur": not_quite_room_for_a_second,
        "call_micro_eur": UPPER_BOUND,
    }


def test_calls_that_start_together_cannot_pass_the_cap_together(database_url):
    async def scenario(pool):
        mock = MockLLM(ModelReply(text="no usage, so every call keeps its upper bound"))
        budget = budget_of(pool)
        budget.match_cap = 3 * UPPER_BOUND + UPPER_BOUND // 2
        calls = [budget.meter(f"p{n}", "cheap", mock)(MESSAGES, TOOLS) for n in range(10)]
        results = await asyncio.gather(*calls, return_exceptions=True)
        return results, len(mock.calls), await booked(pool)

    results, sent, rows = with_pool(database_url, scenario)

    assert [type(result) for result in results].count(MatchPaused) == 7
    assert sent == 3
    assert sum(row[-1] for row in rows) == 3 * UPPER_BOUND


def test_prompt_that_could_be_longer_than_the_input_limit_is_not_sent(database_url):
    async def scenario(pool):
        mock = MockLLM(PLAY_3)
        call = budget_of(pool, max_input_tokens=INPUT_BOUND - 1).meter("p1", "cheap", mock)
        with pytest.raises(ModelError) as error:
            await call(MESSAGES, TOOLS)
        fits = budget_of(pool, max_input_tokens=INPUT_BOUND).meter("p1", "cheap", mock)
        await fits(MESSAGES, TOOLS)
        return error.value, len(mock.calls), len(await booked(pool))

    error, sent, rows = with_pool(database_url, scenario)

    # A retry cannot help, so the seat goes to the random bot.
    assert (error.reason, error.retryable) == ("PromptTooLong", False)
    assert (sent, rows) == (1, 1)


def situation(messages):
    block = re.search(r"<situation>\n(.*)\n</situation>", messages[1]["content"]).group(1)
    return json.loads(block)


def lowest_card(messages, tools):
    """A mock model that plays its lowest card and reports 1000 + 100 tokens: 1200 a call."""
    card = min(situation(messages)["hand"])
    return tool_call("play_card", {"card": card}, usage=Usage(1000, 100))


def metered_match(pool, match_id, *, seed=4, **settings):
    """A match of three mock models whose calls go through one budget."""
    plugin = ToyGame()
    budget = budget_of(pool, match_id=match_id, **settings)
    mocks = {player: MockLLM(lowest_card) for player in PLAYERS}
    agents = {
        player: ModelAgent(budget.meter(player, "cheap", mock), plugin, sleep=no_pause)
        for player, mock in mocks.items()
    }
    sink = partial(EventStore(pool).append, match_id)
    return Match(plugin, agents, seed=seed, sink=sink), budget, mocks


def game_events(events):
    return [event for event in events if event.source is EventSource.GAME]


def test_match_pauses_at_its_cap_and_finishes_when_the_user_allows_more(database_url):
    match_id = uuid4()

    async def scenario(pool):
        match, budget, mocks = metered_match(pool, match_id)
        budget.match_cap = 6000
        with pytest.raises(MatchPaused) as pause:
            await match.run()
        at_pause = {
            "pause": pause.value,
            "sent": sum(len(mock.calls) for mock in mocks.values()),
            "rows": await booked(pool),
            "stored": await EventStore(pool).load(match_id),
            "state": match.state.model_copy(deep=True),
        }
        budget.match_cap = 1_000_000
        placements = await match.run()
        unmetered = Match(
            ToyGame(),
            {player: ModelAgent(MockLLM(lowest_card), ToyGame()) for player in PLAYERS},
            seed=4,
        )
        await unmetered.run()
        return at_pause, match, placements, unmetered, await EventStore(pool).load(match_id)

    at_pause, match, placements, unmetered, stored = with_pool(database_url, scenario)

    pause = at_pause["pause"]
    spent = sum(row[-1] for row in at_pause["rows"])
    assert pause.reason == "match_cap"
    assert pause.data["spent_micro_eur"] == spent == 1200 * at_pause["sent"]
    assert pause.data["cap_micro_eur"] == 6000
    # It paused in the middle of the match, before the call that could pass the
    # cap: what was spent plus the worst case of that call did not fit.
    assert 0 < at_pause["sent"] < CALLS_PER_MATCH
    assert spent <= 6000 < spent + pause.data["call_micro_eur"]
    # The stored log ends with the pause and rebuilds the state the match waits in.
    assert at_pause["stored"][-1].type == "match_paused"
    assert at_pause["stored"][-1].data == {"reason": "match_cap", **pause.data}
    assert replay(ToyGame(), at_pause["stored"]) == at_pause["state"]
    # After the user's decision it plays to the end, and the pause changed nothing in the game.
    assert sorted(p.player for p in placements) == PLAYERS
    assert stored == match.events
    assert [e.type for e in stored if e.type.startswith("match_")] == [
        "match_started",
        "match_paused",
        "match_resumed",
        "match_finished",
    ]
    assert game_events(stored) == game_events(unmetered.events)


def test_seat_whose_prompt_is_too_long_goes_to_the_random_bot_for_free(database_url):
    async def scenario(pool):
        match, _, mocks = metered_match(pool, uuid4(), max_input_tokens=200)
        await match.run()
        return match, sum(len(mock.calls) for mock in mocks.values()), await booked(pool)

    match, sent, rows = with_pool(database_url, scenario)

    failures = [event.data for event in match.events if event.type == "agent_failed"]
    assert failures == [
        {"player": player, "error": "model call failed after 1 tries (PromptTooLong)"}
        for player in PLAYERS
    ]
    assert match.events[-1].type == "match_finished"
    assert (sent, rows) == (0, [])


def test_real_model_from_the_config_is_metered(database_url, answer_with):
    sent = answer_with(mock_response="I just talk.")

    async def scenario(pool):
        reply = await budget_of(pool).model("p1", "cheap")(MESSAGES, TOOLS)
        return reply, await booked(pool)

    reply, rows = with_pool(database_url, scenario)

    assert sent["model"] == "openrouter/some-vendor/cheap-model"
    assert sent["max_tokens"] == MAX_OUTPUT
    assert "reasoning_effort" not in sent  # this config leaves it to the model
    # LiteLLM's mock counts 10 tokens of prompt and 20 of answer.
    assert reply.usage == Usage(10, 20)
    assert [row[1:] for row in rows] == [("p1", "cheap", 10, 20, 10 * 1 + 20 * 2)]


def test_real_model_is_asked_with_the_reasoning_effort_of_the_config(database_url, answer_with):
    sent = answer_with(mock_response="I just talk.")
    short = config().limits.model_copy(update={"reasoning_effort": "low"})
    settings = config().model_copy(update={"limits": short})

    async def scenario(pool):
        await Budget(Ledger(pool), uuid4(), settings).model("p1", "cheap")(MESSAGES, TOOLS)

    with_pool(database_url, scenario)

    assert sent["reasoning_effort"] == "low"


def test_no_key_prompt_or_provider_text_reaches_logs_events_or_the_ledger(
    database_url, litellm, answer_with, monkeypatch, caplog, capfd
):
    key = "THIS-IS-THE-SECRET-KEY"  # not shaped like a real key, so secret scanners stay quiet
    monkeypatch.setenv("OPENROUTER_API_KEY", key)
    caplog.set_level(logging.DEBUG)  # as loud as logging gets
    answer_with(
        mock_response=litellm.AuthenticationError(
            message=f"Incorrect API key provided: {key}",
            model="some-vendor/cheap-model",
            llm_provider="openrouter",
        )
    )
    match_id = uuid4()

    async def scenario(pool):
        plugin = ToyGame()
        budget = budget_of(pool, match_id=match_id)
        agents = {player: ModelAgent(budget.model(player, "cheap"), plugin) for player in PLAYERS}
        match = Match(plugin, agents, seed=4, sink=partial(EventStore(pool).append, match_id))
        await match.run()
        return await EventStore(pool).load(match_id), await booked(pool)

    stored, rows = with_pool(database_url, scenario)

    # Every seat lost its model at the first call, and the log says only what kind of failure.
    assert [event.data["error"] for event in stored if event.type == "agent_failed"] == [
        "model call failed after 1 tries (AuthenticationError)"
    ] * len(PLAYERS)
    printed = capfd.readouterr()
    everything = "\n".join(
        [caplog.text, printed.out, printed.err, repr(rows)]
        + [json.dumps(event.model_dump(mode="json")) for event in stored]
    )
    assert "THIS-IS-THE-SECRET-KEY" not in everything
    assert "Incorrect API key" not in everything
    # Prompts hold what a player may see and nobody else: they do not belong in logs either.
    assert "You are player" not in caplog.text + printed.out + printed.err


def test_a_model_with_its_own_output_limit_is_booked_at_that_limit(database_url):
    async def scenario(pool):
        for model_id in ("cheap", "long"):
            call = budget_of(pool).meter("p1", model_id, MockLLM(ModelReply(text="no usage")))
            await call(MESSAGES, TOOLS)
        rows = await pool.fetch("SELECT model, cost_micro_eur FROM model_calls ORDER BY id")
        return {row["model"]: row["cost_micro_eur"] for row in rows}

    costs = with_pool(database_url, scenario)

    assert costs == {"cheap": UPPER_BOUND, "long": UPPER_BOUND + 3 * MAX_OUTPUT * 2}


def test_each_call_keeps_how_long_it_took_and_how_much_it_thought(database_url):
    ticks = iter([10.0, 12.5, 20.0, 20.25])  # sent, answered; sent, answered

    async def scenario(pool):
        budget = Budget(
            Ledger(pool), uuid4(), config(), now=lambda: NOVEMBER, clock=lambda: next(ticks)
        )
        call = budget.meter(
            "p1",
            "cheap",
            MockLLM(
                tool_call("play_card", {"card": 3}, usage=Usage(120, 30, reasoning_tokens=12)),
                ModelReply(text="no usage reported"),
            ),
        )
        await call(MESSAGES, TOOLS)
        await call(MESSAGES, TOOLS)
        rows = await pool.fetch(
            "SELECT latency_ms, reasoning_tokens, cost_micro_eur FROM model_calls ORDER BY id"
        )
        return [tuple(row.values()) for row in rows]

    rows = with_pool(database_url, scenario)

    assert rows == [(2500, 12, 120 * 1 + 30 * 2), (250, None, UPPER_BOUND)]


def test_a_ledger_without_the_time_columns_still_settles_the_cost(database_url):
    async def scenario(pool):
        await pool.execute("ALTER TABLE model_calls DROP COLUMN latency_ms")
        await pool.execute("ALTER TABLE model_calls DROP COLUMN reasoning_tokens")
        call = budget_of(pool).meter(
            "p1",
            "cheap",
            MockLLM(
                tool_call("play_card", {"card": 3}, usage=Usage(120, 30, reasoning_tokens=12)),
                ModelReply(text="no usage reported"),
            ),
        )
        first = await call(MESSAGES, TOOLS)
        await call(MESSAGES, TOOLS)
        return first, await booked(pool)

    first, rows = with_pool(database_url, scenario)

    assert first.tool_calls  # the answer came through: the turn is not lost
    assert [row[-1] for row in rows] == [120 * 1 + 30 * 2, UPPER_BOUND]


def test_a_rate_limited_call_costs_nothing_but_a_failed_one_keeps_its_bound(database_url):
    async def scenario(pool):
        call = budget_of(pool).meter(
            "p1", "cheap", MockLLM(ModelError("RateLimitError"), ModelError("Timeout"))
        )
        for _ in range(2):
            with pytest.raises(ModelError):
                await call(MESSAGES, TOOLS)
        rows = await pool.fetch("SELECT cost_micro_eur FROM model_calls ORDER BY id")
        return [row["cost_micro_eur"] for row in rows]

    # Refused before anything was generated: void. A timeout may have been billed: kept.
    assert with_pool(database_url, scenario) == [0, UPPER_BOUND]
