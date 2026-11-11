"""Fixtures for tests that go through the real LiteLLM library, without any network."""

import asyncio
import socket

import pytest

from arena.agents.litellm_model import LiteLLMModel
from arena.agents.model import ModelError


@pytest.fixture(scope="module")
def litellm():
    """LiteLLM, loaded the way the wrapper loads it, with every name lookup refused.

    No test of a module that uses this may reach the network: not the import,
    not a call.
    """
    lookups = []

    def refuse(host, *args, **kwargs):
        lookups.append(host)
        raise OSError("These tests must not use the network")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket, "getaddrinfo", refuse)
        # The first call through the wrapper imports LiteLLM.
        with pytest.raises(ModelError):
            asyncio.run(LiteLLMModel("no-such-provider/model", max_output_tokens=1)([], []))
        import litellm

        yield litellm
    assert lookups == []


@pytest.fixture
def answer_with(litellm, monkeypatch):
    """Make LiteLLM answer the next calls with a mock response. Returns what it was sent."""
    real = litellm.acompletion
    sent = {}

    def install(**mock):
        async def acompletion(**arguments):
            sent.update(arguments)
            return await real(**arguments, **mock)

        monkeypatch.setattr(litellm, "acompletion", acompletion)
        return sent

    return install
