"""Model qualification jobs (research/QUALIFY.md): POST to start one, GET to read results.

Starting a job spends money like a match with model seats and has exactly its guards:
ARENA_ALLOW_MODEL_SEATS=1 (403), confirm_spend (422), the provider's key (503) and a
durable ledger (503). The job books every call in the ledger under its own id, against a
per-click cap (default EUR 0.01, at most the per-match cap) and the month cap; it is not a
match and leaves no match record, replay or batch. One job runs at a time.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from arena.agents.budget import MICRO, Budget
from arena.agents.model import ModelCall
from arena.agents.runner import MAX_RETRIES
from arena.api.matches import ALLOW_MODEL_SEATS, Live, _seat_config
from arena.config import Config, load_keys
from arena.db.qualification_store import Qualification, QualificationStore
from arena.engine.plugin import GamePlugin
from arena.qualify.fixtures import Fixture
from arena.qualify.manifest import MANIFESTS
from arena.qualify.runner import (
    FRESH_DAYS,
    SCOPE,
    as_json,
    bound_micro_eur,
    config_hash,
    configuration,
    fixtures_of,
    requests_of,
    run_job,
    settings_of,
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["qualification"])
CLICK_CAP_EUR = 0.01  # QUALIFY.md: the default cap of one "Test this model" click


class NewQualification(BaseModel):
    model: str = Field(description="Exact model id of GET /models/catalog, suffix included")
    game: str = Field(description="Game id; games with a core manifest: liars_deck, poker")
    answer_repair: Literal["off", "v1"] = Field(
        "off", description="Tested as configured: off and v1 are separate results"
    )
    thought_headline: bool = False
    confirm_spend: bool = Field(False, description="This click spends money: true to start it")
    max_eur: float = Field(
        CLICK_CAP_EUR,
        gt=0,
        description="What this click may spend at most, euros; at most the per-match cap. "
        "A job whose worst case does not fit is refused, never shrunk",
    )
    parent_id: UUID | None = Field(None, description="The failed job this one retries")


class Current(BaseModel):
    status: str = Field(description="qualified, unqualified or unknown, for this configuration")
    badge: str | None
    reason: str | None = Field(description="Why unknown: never tested, expired, changed")
    config_hash: str
    last: Qualification | None = Field(
        description="The result the status comes from: the newest decisive one, if any"
    )
    latest: Qualification | None = Field(
        description="The newest attempt of this configuration, whatever its outcome: a later "
        "unknown shows here, and never refreshes the decisive result or its expiry"
    )


class Jobs:
    """The qualification results and the running job (one at a time)."""

    def __init__(self, store: QualificationStore):
        self.store = store
        self.lock = asyncio.Lock()
        self.task: asyncio.Task | None = None

    async def stop(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


def _jobs(request: Request) -> Jobs:
    return request.app.state.qualifications


@cache
def _fixtures(game: str, version: str) -> dict[str, Fixture | None]:
    """A game's fixtures; rebuilt only when the game's version changes (or the process)."""
    from arena.games import load_games

    return fixtures_of(load_games()[game], MANIFESTS[game])


async def _prepared(plugin: GamePlugin, config: Config, model_id: str, settings: dict[str, Any]):
    fixtures = await asyncio.to_thread(_fixtures, plugin.id, plugin.version)
    sent = await requests_of(plugin, fixtures, settings)
    conf = configuration(plugin, MANIFESTS[plugin.id], fixtures, sent, config, model_id, settings)
    return fixtures, sent, conf


def _plugin(live, game: str) -> GamePlugin:
    plugin = live.games.get(game)
    if plugin is None:
        raise HTTPException(404, f"Unknown game {game!r}. Games: {', '.join(live.games)}")
    if game not in MANIFESTS or game == "toy":
        ready = ", ".join(g for g in MANIFESTS if g != "toy")
        raise HTTPException(422, f"{game} has no core qualification manifest yet ({ready} do).")
    return plugin


def model_call(budget: Budget, case: str, model_id: str) -> ModelCall:
    """The real, metered call of the model; tests replace it with a metered mock."""
    return budget.model(f"q-{case}", model_id)


@router.post("/qualifications", status_code=202)
async def start_qualification(new: NewQualification, request: Request, live: Live) -> Qualification:
    """Start a core qualification job for one model and game. Spends money; see the guards."""
    plugin = _plugin(live, new.game)
    if os.environ.get(ALLOW_MODEL_SEATS) != "1":
        raise HTTPException(
            403,
            f"Qualification makes paid calls and is off on this server. Start it with "
            f"{ALLOW_MODEL_SEATS}=1 to allow it.",
        )
    if not new.confirm_spend:
        raise HTTPException(422, "A qualification spends money: send confirm_spend: true.")
    config = await _seat_config([new.model])
    if missing := load_keys(config, [new.model]):
        raise HTTPException(
            503, f"The server lacks {', '.join(missing)}, the provider's API key. Nothing started."
        )
    if new.max_eur > float(config.limits.match_eur):
        raise HTTPException(
            422, f"max_eur is at most the per-match cap of {config.limits.match_eur} euros."
        )
    await live.ledger.check(await live.matches.model_matches())  # 503 when it is not durable
    jobs = _jobs(request)
    async with jobs.lock:
        if jobs.task is not None and not jobs.task.done():
            raise HTTPException(409, "A qualification is running. Try again when it has ended.")
        settings = settings_of(new.answer_repair, new.thought_headline)
        fixtures, sent, conf = await _prepared(plugin, config, new.model, settings)
        cap = int(new.max_eur * MICRO)
        bound = bound_micro_eur(config, new.model, sent)
        if bound > cap:
            raise HTTPException(
                422,
                f"Its worst case is {bound / MICRO:.6f} euros, above max_eur "
                f"{new.max_eur}: send a max_eur of at least that to run it.",
            )
        job_id, now = uuid4(), datetime.now(UTC)
        store = jobs.store
        await store.start(
            job_id,
            model_id=new.model,
            game=new.game,
            scope=SCOPE,
            config_hash=config_hash(conf),
            configuration=conf,
            reserved_micro_eur=bound,
            cap_micro_eur=cap,
            parent_id=new.parent_id,
            now=now,
        )
        budget = Budget(live.ledger, job_id, config)
        budget.match_cap = min(budget.match_cap, cap)  # the smaller cap wins, for the whole job
        jobs.task = asyncio.create_task(
            _run(store, job_id, plugin, fixtures, budget, new.model, settings)
        )
    record = await store.get(job_id)
    assert record is not None
    return record


async def _run(store, job_id, plugin, fixtures, budget, model_id, settings) -> None:
    try:
        verdict = await run_job(
            plugin,
            MANIFESTS[plugin.id],
            fixtures,
            lambda case: model_call(budget, case, model_id),
            settings,
        )
        status, badge, reasons = verdict.status, verdict.badge, verdict.reasons
        cases, counts = as_json(verdict), verdict.counts
    except Exception as error:  # noqa: BLE001 - the job's result is unknown, not lost
        log.exception("Qualification %s failed", job_id)
        status, badge, reasons, cases, counts = (
            "unknown",
            None,
            [f"job failed ({type(error).__name__})"],
            [],
            {},
        )
    now = datetime.now(UTC)
    await store.finish(
        job_id,
        status=status,
        badge=badge,
        reasons=reasons,
        cases=cases,
        counts=counts,
        now=now,
        expires_at=now + timedelta(days=FRESH_DAYS),
    )


@router.get("/qualifications")
async def list_qualifications(
    request: Request, model: str | None = None, game: str | None = None
) -> list[Qualification]:
    """Qualification results, newest first; filter by model and game. Read-only."""
    return await _jobs(request).store.recent(model, game)


class Quote(BaseModel):
    model: str
    game: str
    answer_repair: str
    scope: str
    cases: list[dict[str, str]] = Field(description="Each core case: its id, check and thought")
    calls: int = Field(description="Model calls of the job, one per case, before retries")
    tries_per_call: int = Field(description="Transport attempts per call the reserve covers")
    reserved_micro_eur: int = Field(description="The job's worst case: what a start reserves")
    default_cap_micro_eur: int = Field(description="The cap of a click unless raised")
    max_cap_micro_eur: int = Field(description="The highest cap a click may set")
    fits_default: bool = Field(description="Whether the worst case fits the default cap")
    config_hash: str


@router.get("/qualifications/quote")
async def quote_qualification(
    live: Live,
    model: str,
    game: str,
    answer_repair: Literal["off", "v1"] = "off",
    thought_headline: bool = False,
) -> Quote:
    """What a "Test this model" click would send and reserve, before anyone confirms it.

    Spends nothing and starts nothing. The worst case covers every case at its booking
    bound and every permitted transport retry; a click whose cap is below it is refused.
    """
    plugin = _plugin(live, game)
    config = await _seat_config([model])
    settings = settings_of(answer_repair, thought_headline)
    fixtures, sent, conf = await _prepared(plugin, config, model, settings)
    bound = bound_micro_eur(config, model, sent)
    default = int(CLICK_CAP_EUR * MICRO)
    return Quote(
        model=model,
        game=game,
        answer_repair=answer_repair,
        scope=SCOPE,
        cases=[
            {
                "case": case.id,
                "check": case.check,
                "thought": "required" if case.thought_required else "optional",
            }
            for case in MANIFESTS[game].cases
            if fixtures.get(case.id) is not None
        ],
        calls=len(sent),
        tries_per_call=1 + MAX_RETRIES,
        reserved_micro_eur=bound,
        default_cap_micro_eur=default,
        max_cap_micro_eur=int(config.limits.match_eur * MICRO),
        fits_default=bound <= default,
        config_hash=config_hash(conf),
    )


@router.get("/qualifications/current")
async def current_qualification(
    request: Request,
    live: Live,
    model: str,
    game: str,
    answer_repair: Literal["off", "v1"] = "off",
    thought_headline: bool = False,
) -> Current:
    """The status of this exact configuration now: its newest fresh result, else unknown.

    Spends nothing. A result of another configuration (another repair setting, another game
    or prompt version, other call options) never counts; an expired one is unknown.
    """
    plugin = _plugin(live, game)
    config = await _seat_config([model])
    _, _, conf = await _prepared(
        plugin, config, model, settings_of(answer_repair, thought_headline)
    )
    rows = await _jobs(request).store.recent(model, game)
    return current(rows, config_hash(conf), datetime.now(UTC))


def current(rows: list[Qualification], hash_: str, now: datetime) -> Current:
    """The newest fresh pass or failure of this configuration; a later outage (unknown)
    never hides it. Without one: the newest unknown, expired or never-tested."""
    same = [r for r in rows if r.config_hash == hash_ and r.status != "running"]
    if not same:
        reason = "configuration changed since the last test" if rows else "never tested"
        return Current(
            status="unknown", badge=None, reason=reason, config_hash=hash_, last=None, latest=None
        )
    latest = same[0]
    decisive = next((r for r in same if r.status in ("qualified", "unqualified")), None)
    if decisive is not None:
        # Its own expiry counts: a later attempt never makes it fresh again.
        if decisive.expires_at is None or decisive.expires_at > now:
            return Current(
                status=decisive.status,
                badge=decisive.badge,
                reason=None,
                config_hash=hash_,
                last=decisive,
                latest=latest,
            )
        return Current(
            status="unknown",
            badge=None,
            reason=f"expired: last tested {decisive.status}",
            config_hash=hash_,
            last=decisive,
            latest=latest,
        )
    return Current(
        status="unknown",
        badge=None,
        reason=latest.reasons[0] if latest.reasons else None,
        config_hash=hash_,
        last=latest,
        latest=latest,
    )


@router.get("/qualifications/{job_id}")
async def get_qualification(job_id: UUID, request: Request) -> Qualification:
    record = await _jobs(request).store.get(job_id)
    if record is None:
        raise HTTPException(404, "Unknown qualification")
    return record
