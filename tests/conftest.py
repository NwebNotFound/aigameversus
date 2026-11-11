"""Shared fixtures: LiteLLM without any network, and a `games` folder a test writes itself."""

import asyncio
import socket
import sys

import pytest

import games
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


@pytest.fixture
def fake_games(tmp_path, monkeypatch):
    """Replace the `games` folder: `fake_games(name=source_of_plugin_py, other=None)`.

    A source of None gives a package without a plugin module.
    """
    installed = []

    def install(**plugins):
        for name, source in plugins.items():
            package = tmp_path / name
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            if source is not None:
                (package / "plugin.py").write_text(source, encoding="utf-8")
            installed.append(name)
        monkeypatch.setattr(games, "__path__", [str(tmp_path)])

    yield install
    for name in installed:
        sys.modules.pop(f"games.{name}.plugin", None)
        sys.modules.pop(f"games.{name}", None)


@pytest.fixture(autouse=True)
def offline_catalog(tmp_path, monkeypatch):
    """No test reaches OpenRouter for its model list: each starts without a cached copy and
    with downloads refused. A test that wants a list writes the cache (see test_catalog)."""
    import arena.catalog

    def refuse():
        raise OSError("These tests must not use the network")

    monkeypatch.setattr(arena.catalog, "_download", refuse)
    monkeypatch.setenv("ARENA_CATALOG_CACHE", str(tmp_path / "catalog-cache.json"))
