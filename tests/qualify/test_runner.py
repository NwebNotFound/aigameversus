"""The qualification runner (research/QUALIFY.md), with mock models only: nothing is spent."""

import asyncio
import json
import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from arena.agents.mock_llm import HANGS, MockLLM, tool_call
from arena.agents.model import ModelError, ModelReply, ToolCall
from arena.config import load_config
from arena.db.qualification_store import Qualification
from arena.engine.types import MatchPaused
from arena.games import load_games
from arena.qualify.manifest import MANIFESTS
from arena.qualify.runner import (
    bound_micro_eur,
    config_hash,
    configuration,
    fixtures_of,
    requests_of,
    run_case,
    run_job,
    settings_of,
    verdict,
)

GAMES = load_games()
FIXTURES = {game: fixtures_of(GAMES[game], MANIFESTS[game]) for game in ("toy", "poker")}
OFF = settings_of("off", False)
V1 = settings_of("v1", False)
THOUGHT = "I keep it short: this is the move."


def legal(game, case, *, thought=THOUGHT, wrap=None):
    """A model that answers the case's fixture with a legal move (the game's random one)."""
    fixture = FIXTURES[game][case]
    action = GAMES[game].random_action(
        fixture.request.observation, list(fixture.request.tools), random.Random(1)
    )
    arguments = dict(action.arguments)
    if thought is not None:
        arguments["thought"] = thought
    raw = json.dumps(arguments) if wrap is None else wrap(json.dumps(arguments))
    return MockLLM(ModelReply(tool_calls=(ToolCall(action.tool, raw),)))


def case(game, case_id, call, settings=OFF, **kwargs):
    return asyncio.run(
        run_case(
            GAMES[game], MANIFESTS[game], case_id, FIXTURES[game][case_id], call, settings, **kwargs
        )
    )


def test_fixtures_are_the_same_on_every_build_and_offer_only_engine_tools():
    again = fixtures_of(GAMES["poker"], MANIFESTS["poker"])

    assert {k: f.sha256 for k, f in again.items()} == {
        k: f.sha256 for k, f in FIXTURES["poker"].items()
    }
    assert [t.name for t in FIXTURES["poker"]["B"].request.tools] == ["raise"]
    assert [t.name for t in FIXTURES["poker"]["D"].request.tools] == ["check"]
    for fixture in FIXTURES["poker"].values():
        assert "table_talk" not in {t.name for t in fixture.request.tools}  # speech never


def test_a_fixture_holds_only_the_players_own_view():
    for fixture in FIXTURES["poker"].values():
        state = fixture.state
        # Exactly what the engine shows p1, never a spectator's state.
        assert fixture.request.observation == GAMES["poker"].get_observation(state, "p1")
        # This hand's hidden cards are nowhere in it (earlier hands' showdowns may name the
        # same cards in the events, so the observation is what is checked).
        seen = json.dumps(fixture.request.observation)
        hidden = [card for p, cards in state.hole.items() if p != "p1" for card in cards]
        assert hidden and not any(f'"{card}"' in seen for card in hidden + list(state.deck))


def test_a_legal_first_answer_with_its_thought_is_a_clean_pass():
    result = case("poker", "B", legal("poker", "B"))

    assert (result.outcome, result.reason, result.tool) == ("clean", None, "raise")
    assert result.thought and result.validator is None


def test_a_tool_without_arguments_still_carries_the_thought_apart():
    result = case("poker", "D", legal("poker", "D"))

    assert (result.outcome, result.tool, result.thought) == ("clean", "check", True)


def test_a_missing_thought_fails_where_required_and_warns_elsewhere():
    required = case("poker", "A", legal("poker", "A", thought=None))
    optional = case("poker", "B", legal("poker", "B", thought=None))

    assert (required.outcome, required.reason) == ("failed", "missing required thought")
    assert (optional.outcome, optional.warning) == ("clean", "no thought")


def test_an_answer_that_needs_repair_fails_with_off_and_passes_labelled_with_v1():
    def garble(raw):
        return f"Here are my arguments: {raw}"  # JSON inside text: v1 reads it

    off = case("poker", "B", legal("poker", "B", wrap=garble), OFF)
    v1 = case("poker", "B", legal("poker", "B", wrap=garble), V1)

    assert off.outcome == "failed" and off.reason.startswith("malformed")
    assert v1.outcome == "repaired" and v1.repairs  # the repair is named
    assert verdict([v1], "v1").badge == "repaired (v1)"
    assert verdict([v1], "v1").status == "qualified"


def test_a_cut_off_answer_fails_even_with_a_legal_call():
    fixture = FIXTURES["poker"]["B"]
    bound = fixture.request.tools[0].parameters["properties"]["amount"]["minimum"]
    cut = MockLLM(
        ModelReply(tool_calls=(ToolCall("raise", json.dumps({"amount": bound})),), cut_off=True)
    )

    result = case("poker", "B", cut)

    assert (result.outcome, result.reason, result.cut_off) == (
        "failed",
        "cut off at the output limit",
        True,
    )


def test_an_illegal_move_fails_with_the_games_or_the_schemas_refusal():
    too_much = MockLLM(tool_call("raise", {"amount": 10**9, "thought": THOUGHT}))
    no_call = MockLLM(ModelReply(text="I would raise."))

    illegal = case("poker", "B", too_much)
    silent = case("poker", "B", no_call)

    assert illegal.outcome == "failed" and illegal.validator
    assert silent.outcome == "failed" and "no tool call" in silent.reason


def test_a_move_the_schema_allows_but_the_rules_do_not_fails_with_the_games_reason():
    hand = FIXTURES["toy"]["A"].request.observation
    not_held = next(card for card in range(1, 1000) if f"{card}" not in json.dumps(hand))

    result = case(
        "toy", "A", MockLLM(tool_call("play_card", {"card": not_held, "thought": THOUGHT}))
    )

    assert result.outcome == "failed" and result.validator  # the game's own refusal
    assert result.reason == f"invalid move: {result.validator}"


@pytest.mark.parametrize(
    ("error", "outcome", "reason"),
    [
        ("RateLimitError", "unknown", "rate limited"),
        ("ServiceUnavailableError", "unknown", "provider unavailable (ServiceUnavailableError)"),
        ("BadRequestError", "failed", "the provider refused the request (BadRequestError)"),
    ],
)
def test_provider_failures_are_unknown_unless_the_provider_refused_the_request(
    error, outcome, reason
):
    retryable = error != "BadRequestError"
    result = case("poker", "B", MockLLM(ModelError(error, retryable=retryable)))

    assert (result.outcome, result.reason) == (outcome, reason)


def test_the_turn_timeout_fails_the_case():
    result = case("poker", "B", MockLLM(HANGS), timeout=0.05)

    assert (result.outcome, result.reason) == ("failed", "model turn timeout (0.05 s)")


def test_unqualified_beats_unknown_beats_qualified():
    passed = case("poker", "B", legal("poker", "B"))
    failed = case("poker", "B", MockLLM(ModelReply(text="nothing")))
    unknown = case("poker", "B", MockLLM(ModelError("RateLimitError", retryable=True)))

    assert verdict([passed, unknown, failed], "off").status == "unqualified"
    assert verdict([passed, unknown], "off").status == "unknown"
    assert verdict([passed, passed], "off").status == "qualified"
    assert verdict([passed], "off").badge is None


def test_a_whole_job_of_legal_answers_qualifies_and_every_case_is_counted():
    manifest = MANIFESTS["toy"]

    result = asyncio.run(
        run_job(GAMES["toy"], manifest, FIXTURES["toy"], lambda c: legal("toy", c), OFF)
    )

    assert (result.status, result.reasons) == ("qualified", [])
    assert result.counts == {"clean": 2, "repaired": 0, "failed": 0, "unknown": 0}
    assert [c.case for c in result.cases] == ["A", "C"]


def test_a_budget_stop_ends_the_job_unknown_and_runs_no_further_case():
    asked = []

    def call_for(case_id):
        async def at_the_cap(messages, tools):
            asked.append(case_id)
            raise MatchPaused("match_cap")

        return at_the_cap

    result = asyncio.run(run_job(GAMES["toy"], MANIFESTS["toy"], FIXTURES["toy"], call_for, OFF))

    assert result.status == "unknown"
    assert [c.reason for c in result.cases] == ["budget stop", "not run: budget stop"]
    assert asked == ["A"]


def test_the_configuration_hash_keys_every_setting_and_nothing_volatile():
    plugin, config = GAMES["poker"], load_config()
    model = next(iter(config.models))

    def hash_of(settings, conf=config, model_id=model):
        sent = asyncio.run(requests_of(plugin, FIXTURES["poker"], settings))
        return config_hash(
            configuration(
                plugin, MANIFESTS["poker"], FIXTURES["poker"], sent, conf, model_id, settings
            )
        )

    base = hash_of(OFF)
    assert base == hash_of(OFF)  # stable
    assert hash_of(V1) != base  # off and v1 are never one verdict
    assert hash_of(settings_of("off", True)) != base  # thought_headline changes the prompt
    longer = config.model_copy(
        update={"limits": config.limits.model_copy(update={"max_output_tokens": 1501})}
    )
    if config.models[model].max_output_tokens is None:
        assert hash_of(OFF, longer) != base
    other = [m for m in config.models if m != model]
    if other:
        assert hash_of(OFF, model_id=other[0]) != base
    sent = asyncio.run(requests_of(plugin, FIXTURES["poker"], OFF))
    conf = configuration(plugin, MANIFESTS["poker"], FIXTURES["poker"], sent, config, model, OFF)
    assert "key" not in json.dumps(conf).lower().replace("monkey", "")


def test_the_worst_case_bound_counts_every_case_and_every_transport_retry():
    plugin, config = GAMES["poker"], load_config()
    model = next(iter(config.models))
    sent = asyncio.run(requests_of(plugin, FIXTURES["poker"], OFF))

    bound = bound_micro_eur(config, model, sent)
    one = bound_micro_eur(config, model, dict(list(sent.items())[:1]))

    assert len(sent) == 4 and bound > one > 0
    assert bound % 4 == 0  # four tries per case: the first and three retries


def _row(status, hash_="h", age_days=0.0, reasons=()):
    now = datetime.now(UTC)
    started = now - timedelta(days=age_days)
    return Qualification(
        id=uuid4(),
        model_id="m",
        game="poker",
        scope="core",
        config_hash=hash_,
        configuration={},
        status=status,
        badge=None,
        reasons=list(reasons),
        cases=[],
        counts={},
        reserved_micro_eur=1,
        cap_micro_eur=10_000,
        parent_id=None,
        started_at=started,
        finished_at=started,
        expires_at=started + timedelta(days=7),
    )


def test_the_current_status_is_the_newest_fresh_result_of_the_same_configuration():
    from arena.api.qualify import current

    now = datetime.now(UTC)
    passed = _row("qualified", age_days=2)
    outage = _row("unknown", age_days=1, reasons=["B: rate limited"])

    assert current([], "h", now).reason == "never tested"
    assert current([_row("qualified", hash_="other")], "h", now).reason == (
        "configuration changed since the last test"
    )
    assert current([outage, passed], "h", now).status == "qualified"  # an outage hides no pass
    assert current([outage], "h", now).status == "unknown"
    old = current([_row("qualified", age_days=8)], "h", now)
    assert (old.status, old.reason) == ("unknown", "expired: last tested qualified")
