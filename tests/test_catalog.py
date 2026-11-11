"""The model catalog: OpenRouter's public list, filtered, cached, merged with the config.

No test reaches the network: `offline_catalog` (tests/conftest.py) refuses every
download, and a test that needs a list hands it over here.
"""

import asyncio
import json
from decimal import Decimal

import pytest

import arena.catalog as catalog
from arena.config import load_config

CONFIG = load_config()
VERIFIED = CONFIG.models["glm-flash"].model  # z-ai/... on OpenRouter

TOOLS = ["max_tokens", "tool_choice", "tools"]


def listed(
    model_id, *, parameters=TOOLS, outputs=("text",), prompt="0.000001", completion="0.000002"
):
    return {
        "id": model_id,
        "name": f"Vendor: {model_id}",
        "context_length": 128000,
        "architecture": {"output_modalities": list(outputs)},
        "pricing": {"prompt": prompt, "completion": completion},
        "top_provider": {"is_moderated": False},
        "supported_parameters": list(parameters),
    }


SAMPLE = [
    listed("acme/plays"),
    listed("acme/thinks", parameters=[*TOOLS, "reasoning"]),
    listed("acme/no-tool-choice", parameters=["tools"]),
    listed("acme/no-tools", parameters=["max_tokens"]),
    listed("acme/draws", outputs=("image",)),
    listed("acme/router", prompt="-1", completion="-1"),
    listed("acme/gratis:free", prompt="0", completion="0"),
    listed("acme/pricey", completion="0.000015"),  # 15 USD per million output tokens
    listed(VERIFIED, parameters=[*TOOLS, "reasoning"]),
]


def serve(monkeypatch, data=SAMPLE):
    """OpenRouter answers with `data`; returns the list of download calls."""
    calls = []

    def download():
        calls.append(1)
        return json.dumps({"data": data}).encode()

    monkeypatch.setattr(catalog, "_download", download)
    return calls


def load(now=1000.0):
    return asyncio.run(catalog.load(CONFIG, now=now))


def by_id(result):
    return {entry.id: entry for entry in result.entries}


def test_only_models_that_write_text_and_take_a_forced_tool_call_are_listed(monkeypatch):
    serve(monkeypatch)

    found = by_id(load())

    assert {"acme/plays", "acme/thinks", "acme/gratis:free", "acme/pricey"} <= set(found)
    for refused in ("acme/no-tool-choice", "acme/no-tools", "acme/draws", "acme/router"):
        assert refused not in found
    plays = found["acme/plays"]
    assert (plays.vendor, plays.context_length, plays.verified) == ("acme", 128000, False)
    assert (plays.input_usd_per_mtok, plays.output_usd_per_mtok) == (Decimal(1), Decimal(2))
    assert found["acme/thinks"].reasoning and not plays.reasoning
    assert found["acme/gratis:free"].free and not plays.free
    assert found["acme/pricey"].high_price and not plays.high_price


def test_config_models_are_verified_under_their_own_id_and_not_listed_twice(monkeypatch):
    serve(monkeypatch)

    found = by_id(load())

    glm = found["glm-flash"]
    assert glm.verified and glm.openrouter_id == VERIFIED
    assert glm.output_usd_per_mtok == CONFIG.models["glm-flash"].output_usd_per_mtok
    assert glm.reasoning and glm.context_length == 128000  # what OpenRouter adds about it
    assert VERIFIED not in found
    assert set(CONFIG.models) <= set(found)


def test_a_fresh_copy_is_used_for_an_hour_then_the_list_is_read_again(monkeypatch):
    calls = serve(monkeypatch)

    load(now=1000.0)
    load(now=1000.0 + catalog.MAX_AGE - 1)
    assert len(calls) == 1
    again = load(now=1000.0 + catalog.MAX_AGE + 1)
    assert len(calls) == 2 and again.fresh


def test_offline_the_last_copy_is_used_and_without_one_the_config_models(monkeypatch):
    serve(monkeypatch)
    load(now=1000.0)
    monkeypatch.setattr(catalog, "_download", lambda: (_ for _ in ()).throw(OSError("offline")))

    stale = load(now=1000.0 + 10 * catalog.MAX_AGE)
    assert "acme/plays" in by_id(stale)
    assert (stale.fetched_at, stale.fresh) == (1000.0, False)

    catalog.cache_path().unlink()
    nothing = load(now=1000.0 + 10 * catalog.MAX_AGE)
    assert set(by_id(nothing)) == set(CONFIG.models)
    assert (nothing.fetched_at, nothing.fresh) == (None, False)


@pytest.mark.parametrize("answer", [b"not json", b'{"no": "data"}', b'{"data": 7}'])
def test_a_broken_answer_is_treated_like_no_answer(monkeypatch, answer):
    monkeypatch.setattr(catalog, "_download", lambda: answer)

    result = load()

    assert set(by_id(result)) == set(CONFIG.models)


def test_resolve_adds_catalog_models_at_their_prices_and_leaves_unknown_ids_unknown(monkeypatch):
    serve(monkeypatch)

    config = asyncio.run(catalog.resolve(CONFIG, ["glm-flash", "acme/plays", "acme/nothing"]))

    added = config.models["acme/plays"]
    assert (added.provider, added.model, added.name) == (
        "openrouter",
        "acme/plays",
        "Vendor: acme/plays",
    )
    margin = catalog.UNVERIFIED_PRICE_MARGIN  # not checked by hand: booked dearer
    assert (added.input_usd_per_mtok, added.output_usd_per_mtok) == (margin, 2 * margin)
    assert config.models["glm-flash"] == CONFIG.models["glm-flash"]  # verified: as checked
    assert "acme/nothing" not in config.models
    assert config.limits == CONFIG.limits


def test_resolve_reads_nothing_when_every_model_is_in_the_config(monkeypatch):
    calls = serve(monkeypatch)

    assert asyncio.run(catalog.resolve(CONFIG, ["glm-flash"])) is CONFIG
    assert calls == []


@pytest.mark.parametrize(
    "price", ["NaN", "Infinity", "-Infinity", "1e400", "0.02", "-0.000001", "", "free"]
)
def test_a_price_that_cannot_be_counted_leaves_the_model_out(monkeypatch, price):
    serve(monkeypatch, [listed("acme/odd", completion=price), listed("acme/plays")])

    found = by_id(load())

    assert "acme/odd" not in found  # 0.02 per token is 20,000 USD per million: a mistake
    assert "acme/plays" in found


def test_only_the_free_variant_of_a_model_is_listed_beside_it(monkeypatch):
    serve(
        monkeypatch, [listed("acme/plays"), listed("acme/plays:free"), listed("acme/plays:batch")]
    )

    assert {"acme/plays", "acme/plays:free"} <= set(by_id(load()))
    assert "acme/plays:batch" not in by_id(load())


def test_every_entry_says_where_its_price_comes_from(monkeypatch):
    serve(monkeypatch)

    found = by_id(load())

    assert found["glm-flash"].price_source == "config/models.yaml"
    assert found["acme/plays"].price_source == "openrouter list"


def test_a_download_larger_than_any_real_list_is_refused(monkeypatch):
    class Huge:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, limit):
            return b"x" * limit

    monkeypatch.undo()  # the real _download, with the network replaced
    monkeypatch.setattr(catalog.urllib.request, "urlopen", lambda *a, **k: Huge())

    with pytest.raises(ValueError, match="larger"):
        catalog._download()
