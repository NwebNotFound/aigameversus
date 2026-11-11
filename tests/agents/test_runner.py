import asyncio

import pytest

from arena.agents import runner
from arena.agents.mock_llm import MockLLM, tool_call
from arena.agents.model import ModelError, ModelReply, ToolCall
from arena.agents.prompt import build_messages, tool_schemas
from arena.agents.runner import ModelAgent
from arena.engine.types import Action, AgentError, Reply, TurnRequest
from games.toy.plugin import PLAY_CARD, ToyGame
from tests.engine.counter_game import SequentialCounter

REQUEST = TurnRequest(player="p1", observation={"hand": [2, 7]}, tools=(PLAY_CARD,), events=())
PLAY_7 = tool_call("play_card", {"card": 7})
RATE_LIMIT = ModelError("ServiceUnavailableError")  # a failure a retry can fix


def ask(*script):
    """Ask a model agent with this script once. Returns its reply, the mock and the pauses."""
    mock, pauses = MockLLM(*script), []

    async def sleep(seconds):
        pauses.append(seconds)

    agent = ModelAgent(mock, ToyGame(), sleep=sleep, jitter=lambda: 0.0)
    try:
        return asyncio.run(agent.act(REQUEST)), mock, pauses
    except AgentError as error:
        return error, mock, pauses


def test_tool_call_is_the_action_and_text_is_the_thought():
    reply, _, _ = ask(tool_call("play_card", {"card": 7}, text=" The 7 should win.\n"))

    assert reply == Reply(
        action=Action(tool="play_card", arguments={"card": 7}), thought="The 7 should win."
    )


def test_thought_inside_the_call_is_the_thought_and_is_not_part_of_the_move():
    reply, _, _ = ask(tool_call("play_card", {"thought": " The 7 should win. ", "card": 7}))

    assert reply == Reply(
        action=Action(tool="play_card", arguments={"card": 7}), thought="The 7 should win."
    )


def test_thought_inside_the_call_wins_over_text_beside_it():
    said = tool_call("play_card", {"thought": "Short and to the point.", "card": 7}, text="Prose.")

    assert ask(said)[0].thought == "Short and to the point."


@pytest.mark.parametrize("inside", ["", "  ", None, 7, ["a"], {"a": 1}])
def test_thought_that_is_empty_or_no_text_is_dropped_and_text_beside_the_call_counts(inside):
    reply, _, _ = ask(tool_call("play_card", {"thought": inside, "card": 7}, text="Beside."))

    assert reply == Reply(action=Action(tool="play_card", arguments={"card": 7}), thought="Beside.")


@pytest.mark.parametrize("text", [None, "", " \n"])
def test_answer_without_text_has_no_thought(text):
    reply, _, _ = ask(tool_call("play_card", {"card": 7}, text=text))

    assert reply.thought is None


def test_model_gets_the_prompt_of_the_turn_and_the_tools():
    _, mock, _ = ask(PLAY_7)

    plugin = ToyGame()
    assert mock.calls == [
        (build_messages("High Card", plugin.rules(), REQUEST), tool_schemas([PLAY_CARD]))
    ]


def test_answer_without_a_tool_call_is_a_problem_and_keeps_the_thought():
    reply, _, _ = ask(ModelReply(text="I play my 7."))

    assert reply == Reply(
        problem="Your answer contained no tool call. Call exactly one tool.",
        thought="I play my 7.",
    )


def test_answer_cut_off_before_its_tool_call_is_told_to_be_short():
    reply, _, _ = ask(ModelReply(text="First I weigh every card in my", cut_off=True))

    assert reply == Reply(
        problem=(
            "Your answer was cut off at the length limit before it called a tool. "
            "Think in one or two short sentences, then call exactly one tool."
        ),
        thought="First I weigh every card in my",
    )


def test_cut_off_answer_that_did_call_a_tool_is_a_move():
    reply, _, _ = ask(ModelReply(tool_calls=(ToolCall("play_card", '{"card": 7}'),), cut_off=True))

    assert reply == Reply(action=Action(tool="play_card", arguments={"card": 7}))


@pytest.mark.parametrize(
    "arguments",
    ["{card: 7}", '{"card": 7', "", "7", "[7]", '"card"', "null", "[" * 100_000],
    ids=["no quotes", "cut off", "empty", "number", "list", "string", "null", "too deep"],
)
def test_arguments_that_are_not_a_json_object_are_a_problem(arguments):
    reply, _, _ = ask(ModelReply(tool_calls=(ToolCall("play_card", arguments),)))

    assert reply == Reply(
        problem=(
            "The arguments of your call to 'play_card' were not a JSON object. "
            "Send them as one JSON object."
        )
    )


def test_only_the_first_of_several_tool_calls_counts():
    both = ModelReply(
        tool_calls=(ToolCall("play_card", '{"card": 2}'), ToolCall("play_card", '{"card": 7}'))
    )

    reply, _, _ = ask(both)

    assert reply.action == Action(tool="play_card", arguments={"card": 2})


def test_failed_call_is_tried_again_after_a_pause():
    reply, mock, pauses = ask(RATE_LIMIT, PLAY_7)

    assert reply.action == Action(tool="play_card", arguments={"card": 7})
    assert len(mock.calls) == 2
    assert mock.calls[0] == mock.calls[1]
    assert pauses == [1.0]


def test_pause_doubles_with_every_retry():
    reply, mock, pauses = ask(RATE_LIMIT, RATE_LIMIT, RATE_LIMIT, PLAY_7)

    assert reply.action == Action(tool="play_card", arguments={"card": 7})
    assert len(mock.calls) == 4
    assert pauses == [1.0, 2.0, 4.0]


def test_agent_gives_up_when_the_last_retry_fails():
    error, mock, pauses = ask(ModelError("APIConnectionError"))

    assert isinstance(error, AgentError)
    assert str(error) == "model call failed after 4 tries (APIConnectionError)"
    assert len(mock.calls) == 4
    assert pauses == [1.0, 2.0, 4.0]


def test_failure_that_a_retry_cannot_fix_is_not_retried():
    error, mock, pauses = ask(ModelError("AuthenticationError", retryable=False), PLAY_7)

    assert isinstance(error, AgentError)
    assert str(error) == "model call failed after 1 tries (AuthenticationError)"
    assert len(mock.calls) == 1
    assert pauses == []


def test_retry_is_logged_without_the_prompt(caplog):
    ask(RATE_LIMIT, PLAY_7)

    assert caplog.messages == ["Model call failed (ServiceUnavailableError), next try in 1 s"]
    assert "hand" not in caplog.text


def test_game_without_rules_cannot_be_played_by_a_model():
    with pytest.raises(FileNotFoundError, match=r"rules\.md"):
        ModelAgent(MockLLM(PLAY_7), SequentialCounter())


def test_mock_llm_repeats_its_last_step_and_needs_a_script():
    mock = MockLLM(RATE_LIMIT, PLAY_7)

    async def three_calls():
        results = []
        for _ in range(3):
            try:
                results.append(await mock([], []))
            except ModelError as error:
                results.append(error)
        return results

    assert asyncio.run(three_calls()) == [RATE_LIMIT, PLAY_7, PLAY_7]
    with pytest.raises(ValueError, match="at least one step"):
        MockLLM()


THROTTLED = ModelError("RateLimitError")
ANSWER = tool_call("play_card", {"card": 7})


def throttled_agent(*script, jitter=0.0):
    """An agent over `script`, and the list its pauses go to."""
    pauses = []

    async def sleep(seconds):
        pauses.append(seconds)

    return ModelAgent(MockLLM(*script), ToyGame(), sleep=sleep, jitter=lambda: jitter), pauses


def test_a_rate_limit_is_waited_out_longer():
    agent, pauses = throttled_agent(THROTTLED, THROTTLED, THROTTLED, ANSWER)

    assert asyncio.run(agent.act(REQUEST)).action is not None
    assert pauses == [3.0, 6.0, 12.0]


def test_every_pause_is_up_to_half_longer_at_random():
    agent, pauses = throttled_agent(RATE_LIMIT, THROTTLED, ANSWER, jitter=1.0)

    asyncio.run(agent.act(REQUEST))

    assert pauses == [1.5, 9.0]  # 1 s and 6 s, each times 1.5


def test_a_seat_waits_out_only_so_many_rate_limits_in_a_match():
    moves = runner.RATE_LIMIT_RETRIES_PER_MATCH // 2  # two rate limits per move
    agent, pauses = throttled_agent(*[THROTTLED, THROTTLED, ANSWER] * moves, THROTTLED)

    for _ in range(moves):
        assert asyncio.run(agent.act(REQUEST)).action is not None
    waited = len(pauses)
    with pytest.raises(AgentError, match="rate-limit retries of this match are used up"):
        asyncio.run(agent.act(REQUEST))

    assert waited == runner.RATE_LIMIT_RETRIES_PER_MATCH
    assert len(pauses) == waited  # the last rate limit is not waited out
