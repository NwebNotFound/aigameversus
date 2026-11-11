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
    # The answer is limited in length, and LiteLLM's own retries are off: the
    # agent runner is the only one that retries.
    assert sent == {
        "model": MODEL,
        "messages": MESSAGES,
        "tools": TOOLS,
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
