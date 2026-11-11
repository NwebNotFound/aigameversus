"""Every OpenRouter model that can take a seat, from OpenRouter's public model list.

A model can play when it answers in text and takes a forced tool call: its
`supported_parameters` hold `tools` and `tool_choice` (the runner sends
`tool_choice: required`). The list needs no key. It is cached in a file for an
hour; when OpenRouter cannot be reached the last copy is used, however old,
and without any copy the catalog is just the models of config/models.yaml.

A model of config/models.yaml is *verified*: its prices were checked by hand
and its id there (`glm-flash`) is the one to use. Every other model goes by its
OpenRouter id (`vendor/model`) at the prices OpenRouter lists, and the caps of
config/models.yaml hold for it like for any model.
"""

import asyncio
import json
import logging
import os
import tempfile
import time
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from arena.config import Config, Model

log = logging.getLogger(__name__)

CATALOG_URL = "https://openrouter.ai/api/v1/models"
MAX_AGE = 3600  # seconds a downloaded list is used before it is fetched again
DOWNLOAD_TIMEOUT = 10
HIGH_OUTPUT_USD_PER_MTOK = Decimal(10)  # above this, the launch form warns
MAX_USD_PER_MTOK = Decimal(10_000)  # a listed price above this is a mistake, not a model
# An unverified model is booked at its listed price times this: nobody checked the price,
# and OpenRouter may route a call to a dearer provider, so the caps stop it early, not late.
UNVERIFIED_PRICE_MARGIN = Decimal("1.25")
MAX_DOWNLOAD_BYTES = 20_000_000  # today's list is under 1 MB
_PER_MTOK = Decimal(1_000_000)


def cache_path() -> Path:
    default = Path(tempfile.gettempdir()) / "aigameversus-openrouter-models.json"
    return Path(os.environ.get("ARENA_CATALOG_CACHE") or default)


@dataclass(frozen=True)
class Entry:
    id: str  # what POST /matches takes: the config id if verified, else the OpenRouter id
    openrouter_id: str
    name: str
    vendor: str
    context_length: int | None
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    reasoning: bool
    moderated: bool
    free: bool
    verified: bool

    @property
    def price_source(self) -> str:
        return "config/models.yaml" if self.verified else "openrouter list"

    @property
    def high_price(self) -> bool:
        return self.output_usd_per_mtok > HIGH_OUTPUT_USD_PER_MTOK


@dataclass(frozen=True)
class Catalog:
    entries: list[Entry]
    fetched_at: float | None  # when the list was downloaded; None: config models only
    fresh: bool  # downloaded within MAX_AGE


def _download() -> bytes:
    request = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "aigameversus"})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
        data = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ValueError("the model list is larger than any real one")
    return data


async def load(config: Config, *, now: float | None = None) -> Catalog:
    """The catalog: from the cache while it is fresh, else downloaded, else the last copy."""
    now = time.time() if now is None else now
    path = cache_path()
    cached = _read_cache(path)
    if cached is not None and now - cached[0] < MAX_AGE:
        return Catalog(entries(config, cached[1]), cached[0], fresh=True)
    try:
        raw = await asyncio.to_thread(_download)
        data = json.loads(raw)["data"]
        if not isinstance(data, list):
            raise ValueError("the list is not a list")
    except (OSError, ValueError, KeyError, TypeError) as error:
        log.warning("OpenRouter's model list cannot be read (%s)", type(error).__name__)
        if cached is None:
            return Catalog(entries(config, []), None, fresh=False)
        return Catalog(entries(config, cached[1]), cached[0], fresh=False)
    _write_cache(path, now, data)
    return Catalog(entries(config, data), now, fresh=True)


def entries(config: Config, data: list[dict[str, Any]]) -> list[Entry]:
    """The models that can play: the verified ones from the config, then OpenRouter's."""
    listed = {item.get("id"): item for item in data if isinstance(item, dict)}
    found = [_verified(key, model, listed.get(model.model)) for key, model in config.models.items()]
    taken = {model.model for model in config.models.values()}
    for item in data:
        entry = _entry(item)
        if entry is not None and entry.openrouter_id not in taken:
            found.append(entry)
    return found


def with_models(config: Config, catalog: Catalog, model_ids: Iterable[str]) -> Config:
    """`config` with those of `model_ids` that are unverified catalog models added to it.

    Their Model has OpenRouter's prices times UNVERIFIED_PRICE_MARGIN; ids that are neither
    in the config nor in the catalog stay unknown, so whoever checks the ids still refuses them.
    """
    wanted = set(model_ids) - set(config.models)
    extra = {
        entry.id: Model(
            provider="openrouter",
            model=entry.openrouter_id,
            name=entry.name,
            input_usd_per_mtok=entry.input_usd_per_mtok * UNVERIFIED_PRICE_MARGIN,
            output_usd_per_mtok=entry.output_usd_per_mtok * UNVERIFIED_PRICE_MARGIN,
        )
        for entry in catalog.entries
        if entry.id in wanted and not entry.verified
    }
    if not extra:
        return config
    return config.model_copy(update={"models": {**config.models, **extra}})


async def resolve(config: Config, model_ids: Iterable[str]) -> Config:
    """`config` able to seat these models: the catalog is read only if one is not in it."""
    model_ids = list(model_ids)
    if all(model_id in config.models for model_id in model_ids):
        return config
    return with_models(config, await load(config), model_ids)


def _entry(item: Any) -> Entry | None:
    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
        return None
    model_id = item["id"]
    if ":" in model_id and not model_id.endswith(":free"):  # :batch and other ways to call it
        return None
    parameters = item.get("supported_parameters") or []
    outputs = (item.get("architecture") or {}).get("output_modalities") or []
    if "tools" not in parameters or "tool_choice" not in parameters or "text" not in outputs:
        return None
    pricing = item.get("pricing") or {}
    try:
        prices = [Decimal(str(pricing[key])) * _PER_MTOK for key in ("prompt", "completion")]
    except (KeyError, InvalidOperation):
        return None
    # "-1" is a router whose price depends on the model; NaN, infinity and absurd numbers
    # are mistakes. None of them can be counted against a cap.
    if not all(price.is_finite() and 0 <= price <= MAX_USD_PER_MTOK for price in prices):
        return None
    return Entry(
        id=model_id,
        openrouter_id=model_id,
        name=str(item.get("name") or model_id),
        vendor=model_id.split("/", 1)[0],
        context_length=item.get("context_length"),
        input_usd_per_mtok=prices[0].normalize(),
        output_usd_per_mtok=prices[1].normalize(),
        reasoning="reasoning" in parameters,
        moderated=bool((item.get("top_provider") or {}).get("is_moderated")),
        free=model_id.endswith(":free") or not any(prices),
        verified=False,
    )


def _verified(key: str, model: Model, listed: dict[str, Any] | None) -> Entry:
    """A model of the config, with what OpenRouter's list adds about it, if it has it."""
    known = _entry(listed) if listed else None
    return Entry(
        id=key,
        openrouter_id=model.model,
        name=model.name or key,
        vendor=model.model.split("/", 1)[0],
        context_length=known.context_length if known else None,
        input_usd_per_mtok=model.input_usd_per_mtok,
        output_usd_per_mtok=model.output_usd_per_mtok,
        reasoning=known.reasoning if known else False,
        moderated=known.moderated if known else False,
        free=not model.input_usd_per_mtok and not model.output_usd_per_mtok,
        verified=True,
    )


def _read_cache(path: Path) -> tuple[float, list[dict[str, Any]]] | None:
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        return float(cached["fetched_at"]), list(cached["data"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cache(path: Path, now: float, data: list[dict[str, Any]]) -> None:
    try:
        path.write_text(json.dumps({"fetched_at": now, "data": data}), encoding="utf-8")
    except OSError as error:
        log.warning("The model list cannot be cached (%s)", type(error).__name__)
