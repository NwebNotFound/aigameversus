"""The LiteLLM wrapper, against the real library but without any network.

LiteLLM answers by itself when a call carries `mock_response`. The tests add
that argument to what the wrapper sends, so LiteLLM's own request handling,
response objects and error classes are the real ones.
"""

import asyncio
import traceback

import pytest

from arena.agents.litellm_model import LiteLLMModel
from arena.agents.model import ModelError, ModelReply, ToolCall, Usage

MODEL = "openrouter/some-vendor/some-model"
MESSAGES = [{"role": "user", "content": "It is your turn."}]
TOOLS = [
    {
        "type": "function",
        "function": {"name": "play_card", "description": "Play.", "parameters": {"type": "object"}},
    }
]
PROVIDER_TEXT = "PROVIDER-TEXT-THAT-QUOTES-THE-REQUEST"


def call(model=MODEL):
    """Call a model through the wrapper. Returns its reply or the ModelError."""
    try:
        return asyncio.run(LiteLLMModel(model, max_output_tokens=300)(MESSAGES, TOOLS))
    except ModelError as error:
        return error


def test_text_and_tool_calls_come_back_as_a_model_reply(answer_with):
    sent = answer_with(
        mock_response="The 3 is enough.",
        mock_tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "play_card", "arguments": '{"card": 3}'},
            }
        ],
    )

    reply = call()

    assert (reply.text, reply.tool_calls) == (
        "The 3 is enough.",
        (ToolCall("play_card", '{"card": 3}'),),
    )
    # The answer is limited in length and has to be a tool call, and LiteLLM's
    # own retries are off: the agent runner is the only one that retries.
    assert sent == {
        "model": MODEL,
        "messages": MESSAGES,
        "tools": TOOLS,
        "tool_choice": "required",
        "max_tokens": 300,
        "num_retries": 0,
    }


def test_reply_carries_the_tokens_the_provider_counted(answer_with):
    answer_with(mock_response="I just talk.")

    # LiteLLM's mock counts 10 tokens of prompt and 20 of answer.
    assert call().usage == Usage(input_tokens=10, output_tokens=20)


def test_reply_without_usage_says_so(litellm, monkeypatch):
    real = litellm.acompletion

    async def acompletion(**arguments):
        response = await real(**arguments, mock_response="I just talk.")
        del response.usage
        return response

    monkeypatch.setattr(litellm, "acompletion", acompletion)

    assert call() == ModelReply(text="I just talk.", usage=None)


def test_answer_without_a_tool_call_has_none(answer_with):
    answer_with(mock_response="I just talk.")

    reply = call()

    assert (reply.text, reply.tool_calls) == ("I just talk.", ())


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        ("RateLimitError", True),
        ("Timeout", True),
        ("APIConnectionError", True),
        ("InternalServerError", True),
        ("ServiceUnavailableError", True),
        ("AuthenticationError", False),
        ("BadRequestError", False),
        ("ContextWindowExceededError", False),
        ("NotFoundError", False),
    ],
)
def test_failed_call_is_a_model_error_that_says_whether_a_retry_can_help(
    litellm, answer_with, error, retryable
):
    answer_with(
        mock_response=getattr(litellm, error)(
            message=PROVIDER_TEXT, model=MODEL, llm_provider="openrouter"
        )
    )

    failure = call()

    assert isinstance(failure, ModelError)
    assert (failure.reason, failure.retryable) == (error, retryable)


def test_unknown_provider_is_an_error_that_a_retry_cannot_fix(litellm, capsys):
    failure = call("no-such-provider/model")

    assert (failure.reason, failure.retryable) == ("BadRequestError", False)
    # LiteLLM's help banners stay out of the output.
    printed = capsys.readouterr()
    assert "Provider List" not in printed.out + printed.err


def test_provider_text_does_not_travel_with_the_error(litellm, answer_with):
    answer_with(
        mock_response=litellm.AuthenticationError(
            message=PROVIDER_TEXT, model=MODEL, llm_provider="openrouter"
        )
    )

    failure = call()

    assert PROVIDER_TEXT not in "".join(traceback.format_exception(failure))


def answer(litellm, *, finish, content, reasoning=None):
    """A provider response as LiteLLM hands it on: how it ended, its text, its reasoning."""
    message = {"role": "assistant", "content": content, "reasoning_content": reasoning}
    return litellm.ModelResponse(
        choices=[{"finish_reason": finish, "index": 0, "message": message}],
        usage={"prompt_tokens": 100, "completion_tokens": 300, "total_tokens": 400},
    )


def test_reasoning_effort_is_sent_only_when_the_model_is_given_one(answer_with):
    sent = answer_with(mock_response="Short.")

    asyncio.run(LiteLLMModel(MODEL, max_output_tokens=300, reasoning_effort="low")(MESSAGES, TOOLS))
    assert sent["reasoning_effort"] == "low"

    sent.clear()
    call()
    assert "reasoning_effort" not in sent


def test_answer_that_ran_into_the_output_limit_is_marked_as_cut_off(litellm, answer_with):
    answer_with(mock_response=answer(litellm, finish="length", content="I think that"))

    reply = call()

    assert (reply.cut_off, reply.text, reply.tool_calls) == (True, "I think that", ())
    assert reply.usage == Usage(100, 300)


def test_finished_answer_is_not_cut_off(litellm, answer_with):
    answer_with(mock_response=answer(litellm, finish="stop", content="The 3 is enough."))

    assert call().cut_off is False


def test_reasoning_is_the_text_of_an_answer_that_has_no_other(litellm, answer_with):
    answer_with(
        mock_response=answer(litellm, finish="length", content=None, reasoning="Hmm, the 3")
    )
    assert call().text == "Hmm, the 3"

    answer_with(
        mock_response=answer(litellm, finish="stop", content="The 3.", reasoning="Long thoughts")
    )
    assert call().text == "The 3."

    answer_with(mock_response=answer(litellm, finish="stop", content=None))
    assert call().text is None


def test_tool_call_is_required_only_when_there_are_tools(answer_with):
    sent = answer_with(mock_response="Short.")

    asyncio.run(LiteLLMModel(MODEL, max_output_tokens=300)(MESSAGES, []))

    assert "tool_choice" not in sent


def refusing(litellm, monkeypatch, refuse):
    """Make LiteLLM refuse the requests for which `refuse(arguments)` holds. Returns all sent."""
    real, sent = litellm.acompletion, []

    async def acompletion(**arguments):
        sent.append(arguments)
        if refuse(arguments):
            raise litellm.BadRequestError(
                message=PROVIDER_TEXT, model=MODEL, llm_provider="openrouter"
            )
        return await real(**arguments, mock_response="Fine.")

    monkeypatch.setattr(litellm, "acompletion", acompletion)
    return sent


def test_request_refused_with_the_options_goes_out_once_more_without_them(litellm, monkeypatch):
    sent = refusing(litellm, monkeypatch, lambda arguments: "tool_choice" in arguments)
    model = LiteLLMModel(MODEL, max_output_tokens=300, reasoning_effort="low")

    reply = asyncio.run(model(MESSAGES, TOOLS))

    assert reply.text == "Fine."
    assert [("tool_choice" in s, "reasoning_effort" in s) for s in sent] == [
        (True, True),
        (False, False),
    ]
    assert sent[1] == {
        "model": MODEL,
        "messages": MESSAGES,
        "tools": TOOLS,
        "max_tokens": 300,
        "num_retries": 0,
    }


def test_request_refused_without_the_options_too_is_an_error_a_retry_cannot_fix(
    litellm, monkeypatch
):
    sent = refusing(litellm, monkeypatch, lambda arguments: True)

    failure = call()

    assert isinstance(failure, ModelError)
    assert (failure.reason, failure.retryable) == ("BadRequestError", False)
    assert len(sent) == 2
    assert PROVIDER_TEXT not in "".join(traceback.format_exception(failure))


def test_request_that_had_no_options_is_not_sent_twice(litellm, monkeypatch):
    sent = refusing(litellm, monkeypatch, lambda arguments: True)

    with pytest.raises(ModelError):
        asyncio.run(LiteLLMModel(MODEL, max_output_tokens=300)(MESSAGES, []))

    assert len(sent) == 1


@pytest.mark.parametrize("error", ["AuthenticationError", "RateLimitError"])
def test_other_failures_are_not_answered_with_a_second_request(litellm, answer_with, error):
    sent = []
    answered = answer_with(
        mock_response=getattr(litellm, error)(
            message=PROVIDER_TEXT, model=MODEL, llm_provider="openrouter"
        )
    )
    real = litellm.acompletion

    async def counting(**arguments):
        sent.append(arguments)
        return await real(**arguments)

    litellm.acompletion = counting
    try:
        failure = call()
    finally:
        litellm.acompletion = real

    assert (failure.reason, len(sent)) == (error, 1)
    assert answered["tool_choice"] == "required"


def test_reasoning_tokens_are_read_when_the_provider_reports_them(litellm, answer_with):
    response = answer(litellm, finish="stop", content="Fine.")
    response.usage = litellm.Usage(
        prompt_tokens=100,
        completion_tokens=300,
        total_tokens=400,
        completion_tokens_details={"reasoning_tokens": 120},
    )
    answer_with(mock_response=response)

    assert call().usage == Usage(100, 300, reasoning_tokens=120)
