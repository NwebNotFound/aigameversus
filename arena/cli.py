"""The `arena` command: play a match in this process and print it as a readable play-by-play.

With `--bots` every seat is a random bot. That needs no server and no
database, and it costs nothing.

With `--models` the seats are models from `config/models.yaml`. That makes
real model calls, which cost money and are counted against the cost caps. The
match, its events and its cost are stored in the database named by
`DATABASE_URL`; the provider's API key comes from the environment.
"""

import argparse
import asyncio
import json
import os
import random
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from arena.agents.budget import MICRO, Budget
from arena.agents.random_bot import random_bots
from arena.agents.runner import ModelAgent
from arena.catalog import resolve
from arena.config import display_name, load_config, load_keys
from arena.db.database import connect, ledger_url, migrate
from arena.db.event_store import EventStore
from arena.db.ledger import Ledger, LedgerUnavailable
from arena.db.match_store import MatchStore, Seat
from arena.engine.match import Match
from arena.engine.plugin import GamePlugin
from arena.engine.replay import replay
from arena.engine.types import Event, MatchPaused, Placement
from arena.games import load_games
from arena.memory.store import MemoryStore
from arena.ratings.store import RatingStore
from arena.transcript import (
    RENDERERS,
    Transcriber,
    TranscriptError,
    display_names,
    from_export,
    labels,
    render_match,
    to_markdown,
    to_text,
)

STOPPED_AT_CAP = 3  # exit code of a match that a cost cap ended early


class _WrongCall(Exception):
    """The command line asks for something that cannot be played. Nothing was started."""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arena", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("games", help="list the games that can be played")
    memory = commands.add_parser("memory", help="what players remember of each other")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)
    reset = memory_commands.add_parser(
        "reset", help="forget relationships and match summaries (ratings stay)"
    )
    reset.add_argument("--profile", metavar="ID", help="only what this profile remembers")
    reset.add_argument(
        "--yes", action="store_true", help="really forget; needed, it cannot be undone"
    )
    show = commands.add_parser(
        "transcript", help="print a stored match, or a saved match file, as a readable play-by-play"
    )
    show.add_argument("source", help="a match id from the database, or a saved match JSON file")
    show.add_argument("--lang", choices=("en", "de"), default="en")
    show.add_argument(
        "--spoilers", action="store_true", help="include hidden cards, roles, thoughts, whispers"
    )
    show.add_argument(
        "--all", action="store_true", help="also bookkeeping lines (hand-overs, deals)"
    )
    show.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    show.add_argument(
        "--follow", action="store_true", help="a match id only: keep printing while it is played"
    )
    run = commands.add_parser("run", help="play one match and print it play-by-play")
    run.add_argument("--game", required=True, help="id of the game, see `arena games`")
    seats = run.add_mutually_exclusive_group(required=True)
    seats.add_argument(
        "--bots",
        action="store_true",
        help="fill every seat with a random bot; costs nothing and stores nothing",
    )
    seats.add_argument(
        "--models",
        metavar="ID,ID,...",
        help="seat these models from config/models.yaml, in this order. Makes paid model "
        "calls, inside the cost caps; needs DATABASE_URL and the provider's API key",
    )
    run.add_argument(
        "--players", type=int, help="with --bots: number of seats (default: the game's minimum)"
    )
    run.add_argument("--seed", type=int, help="seed of the match (default: a random one)")
    run.add_argument(
        "--setting",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="a game setting; the value is read as JSON, or as text if it is not JSON",
    )
    run.add_argument(
        "--turn-timeout",
        type=float,
        metavar="SECONDS",
        help="how long one turn may take, corrections included (default: 60)",
    )
    run.add_argument("--lang", choices=("en", "de"), default="en", help="language of the lines")
    run.add_argument(
        "--no-spoilers", action="store_true", help="print only what every player could see"
    )
    run.add_argument(
        "--all", action="store_true", help="also bookkeeping lines (hand-overs, deals)"
    )
    run.add_argument("--raw", action="store_true", help="print the raw events, as stored")
    run.add_argument(
        "--save",
        metavar="FILE",
        help="with --models: also write the match to this JSON file: "
        "seats, result, cost and every event",
    )
    args = parser.parse_args(argv)

    # Event data can hold any character; a console that cannot show one must not stop a match.
    # Lines go out as they are printed, so a match written to a file can be followed.
    sys.stdout.reconfigure(errors="backslashreplace", line_buffering=True)
    games = load_games()
    if args.command == "memory":
        try:
            return asyncio.run(_reset_memory(args.profile, args.yes))
        except _WrongCall as error:
            parser.error(str(error))
    if args.command == "games":
        for game in games.values():
            print(f"{game.id:<12} {game.name} ({game.min_players} to {game.max_players} players)")
        return 0

    if args.command == "transcript":
        try:
            return asyncio.run(_transcript(args))
        except (TranscriptError, _WrongCall) as error:
            parser.error(str(error))

    if args.game not in games:
        parser.error(f"unknown game {args.game!r}; choose from: {', '.join(games)}")
    plugin = games[args.game]
    try:
        options: dict[str, Any] = {
            "seed": random.SystemRandom().randrange(2**31) if args.seed is None else args.seed,
            "settings": _settings(args.setting),
        }
        if args.turn_timeout is not None:
            options["turn_timeout"] = args.turn_timeout
        if args.models is None:
            if args.save:
                raise _WrongCall("--save goes with --models; a bot match is printed, not stored")
            return _play_bots(plugin, args.players, options, args)
        if args.players is not None:
            raise _WrongCall("--players goes with --bots; with --models every model takes a seat")
        return asyncio.run(_play_models(plugin, args.models.split(","), options, args.save, args))
    except _WrongCall as error:
        parser.error(str(error))


async def _reset_memory(profile: str | None, yes: bool) -> int:
    try:
        profile_id = None if profile is None else UUID(profile)
    except ValueError:
        raise _WrongCall(f"--profile needs a profile id, got {profile!r}") from None
    if not yes:
        raise _WrongCall("memory reset forgets for good; add --yes to do it")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise _WrongCall("memory reset needs DATABASE_URL")
    pool = await connect(url)
    try:
        await migrate(pool)
        done = await MemoryStore(pool).reset(profile_id)
    finally:
        await pool.close()
    whose = "every player" if profile_id is None else f"profile {profile_id}"
    print(
        f"Forgot {done.relationships} relationships and {done.memories} match memories of {whose}."
    )
    return 0


def _play_bots(
    plugin: GamePlugin, count: int | None, options: dict[str, Any], args: argparse.Namespace
) -> int:
    players = [f"p{seat}" for seat in range(1, (count or plugin.min_players) + 1)]
    seed = options["seed"]
    match = _match(
        plugin,
        random_bots(plugin, players, seed),
        options,
        _printer(plugin.id, display_names({p: ("bot", p) for p in players}), args),
    )
    print(f"{plugin.name} ({plugin.id}), players {' '.join(players)}, seed {seed}")
    placements = asyncio.run(match.run())
    if args.raw:  # the play-by-play already ends with the result
        print(_result(placements))
    return 0


async def _play_models(
    plugin: GamePlugin,
    model_ids: Sequence[str],
    options: dict[str, Any],
    save: str | None,
    args: argparse.Namespace,
) -> int:
    config = await resolve(load_config(), model_ids)
    unknown = [model_id for model_id in model_ids if model_id not in config.models]
    if unknown:
        raise _WrongCall(
            f"unknown model {', '.join(unknown)}; config/models.yaml has: "
            f"{', '.join(config.models)}"
        )
    if missing := load_keys(config, model_ids):
        raise _WrongCall(
            f"--models needs {', '.join(missing)} in the environment, the provider's API key. "
            "Nothing was sent or booked"
        )
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise _WrongCall(
            "--models needs DATABASE_URL: the match, its events and what it costs are stored"
        )
    seats = {f"p{seat}": model_id for seat, model_id in enumerate(model_ids, start=1)}
    match_id = uuid4()
    pool = await connect(url)
    ledger_pool = pool if ledger_url(url) == url else await connect(ledger_url(url), min_size=0)
    try:
        await migrate(pool)
        matches, log, ledger = MatchStore(pool), EventStore(pool), Ledger(ledger_pool)
        try:
            await ledger.check(await matches.model_matches())
        except LedgerUnavailable as down:
            raise _WrongCall(f"{down} Nothing was sent or booked") from down
        budget = Budget(ledger, match_id, config)

        async def store_and_print(first_seq: int, events: Sequence[Event]) -> None:
            await log.append(match_id, first_seq, events)
            await show(first_seq, events)

        show = _printer(plugin.id, labels(seats), args)
        agents = {
            player: ModelAgent(budget.model(player, model_id), plugin, settings=options["settings"])
            for player, model_id in seats.items()
        }
        match = _match(plugin, agents, options, store_and_print)
        await matches.create(
            match_id,
            plugin.id,
            list(seats),
            match.seed,
            match.settings,
            seats={
                player: Seat(name=display_name(config, model), model_id=model, kind="model")
                for player, model in seats.items()
            },
            prompt_version=plugin.prompt_version(match.settings),
        )
        print(f"{plugin.name} ({plugin.id}), match {match_id}, seed {match.seed}")
        print("Seats: " + "  ".join(f"{player} {model}" for player, model in seats.items()))
        placements = None
        try:
            placements = await match.run()
        except MatchPaused as pause:
            # Nobody is here to allow more money, so a cap ends the match.
            await matches.close(match_id, "interrupted")
            print(
                f"Stopped at a cost cap ({pause.reason}): {json.dumps(pause.data)}. "
                "The call that would have passed it was not sent."
            )
        except BaseException:
            await matches.close(match_id, "failed")
            raise
        else:
            await matches.close(match_id, "finished", placements)
            if args.raw:
                print(_result(placements))
            note = await _rate_models(pool, match_id, plugin.id, seats, placements)
            if note:
                print(note)

        costs = await ledger.match_costs(match_id)
        stored = await log.load(match_id)
        rebuilt = replay(plugin, stored) == match.state
        spent = "  ".join(f"{player} {_euros(costs.get(player, 0))}" for player in seats)
        print(
            f"Cost: {spent}  total {_euros(sum(costs.values()))} EUR "
            f"of {_euros(budget.match_cap)} EUR"
        )
        print(
            f"Replay: the {len(stored)} stored events "
            + ("rebuild the final state" if rebuilt else "DO NOT rebuild the final state")
        )
        if save:
            export = {
                "match": str(match_id),
                "game": plugin.id,
                "version": plugin.version,
                "seed": match.seed,
                "settings": match.settings,
                "prompt_version": plugin.prompt_version(match.settings),
                "seats": seats,
                "status": "finished" if placements is not None else "stopped_at_cost_cap",
                "placements": [placement.model_dump() for placement in placements or []],
                "cost_micro_eur": costs,
                "events": [event.model_dump(mode="json") for event in stored],
            }
            text = json.dumps(export, ensure_ascii=False, indent=1) + "\n"
            Path(save).write_text(text, encoding="utf-8", newline="\n")
        if not rebuilt:
            return 1
        return 0 if placements is not None else STOPPED_AT_CAP
    finally:
        if ledger_pool is not pool:
            await ledger_pool.close()
        await pool.close()


async def _rate_models(
    pool: Any, match_id: UUID, game: str, seats: dict[str, str], placements: Sequence[Placement]
) -> str | None:
    """Rate a finished model match: one profile per model, the same in every match (D-081).

    Returns a sentence when the match is not rated, else None. A profile is rated once
    per match, so a model in several seats leaves the match unrated.
    """
    models = list(seats.values())
    if len(set(models)) != len(models):
        repeated = sorted({m for m in models if models.count(m) > 1})
        return (
            f"Not rated: {', '.join(repeated)} sits in several seats, "
            "and a model is rated once per match"
        )
    store = RatingStore(pool)
    profiles = {seat: await store.model_profile(model) for seat, model in seats.items()}
    await store.apply_match_result(
        match_id,
        game,
        [Placement(player=str(profiles[p.player]), rank=p.rank) for p in placements],
        seats=profiles,
    )
    return None


def _match(plugin: GamePlugin, agents: dict, options: dict[str, Any], sink: Any) -> Match:
    try:
        return Match(plugin, agents, sink=sink, **options)
    except ValueError as error:  # a player count or a setting the game refuses
        raise _WrongCall(str(error)) from None


def _result(placements: Sequence[Placement]) -> str:
    ranking = sorted(placements, key=lambda placement: placement.rank)
    return "Result: " + "  ".join(f"{placement.rank}. {placement.player}" for placement in ranking)


def _euros(micro_eur: int) -> str:
    return f"{micro_eur / MICRO:.6f}"


def _settings(pairs: Sequence[str]) -> dict[str, Any]:
    settings = {}
    for pair in pairs:
        name, separator, value = pair.partition("=")
        if not separator:
            raise _WrongCall(f"--setting needs NAME=VALUE, got {pair!r}")
        try:
            settings[name] = json.loads(value)
        except ValueError:
            settings[name] = value
    return settings


def _printer(game: str, players: Any, args: argparse.Namespace) -> Any:
    """The sink that prints the events of each turn: play-by-play lines, or raw with --raw."""
    if args.raw:
        return _print_events
    transcriber = Transcriber(game, players, args.lang, not args.no_spoilers)
    state = {"started": False}

    async def show(first_seq: int, events: Sequence[Event]) -> None:
        for seq, event in enumerate(events, start=first_seq):
            line = transcriber.line(event, seq)
            if line is None or (line.importance < 2 and not args.all):
                continue
            if line.kind == "heading" and state["started"]:
                print()
            state["started"] = True
            print(line.text)
            if line.detail:
                print(f"    {line.detail}")

    return show


async def _print_events(first_seq: int, events: Sequence[Event]) -> None:
    """Print the events of one turn raw, one line each: position, type, data, who may see it."""
    for seq, event in enumerate(events, start=first_seq):
        if event.visible_to is None:
            audience = ""
        elif event.visible_to:
            audience = f"  [only {', '.join(event.visible_to)}]"
        else:
            audience = "  [spectators only]"
        data = json.dumps(event.data, ensure_ascii=False)
        print(f"{seq:>4}  {event.type:<16} {data}{audience}")


async def _transcript(args: argparse.Namespace) -> int:
    """`arena transcript`: a saved match file or a stored match, printed once or followed."""
    path = Path(args.source)
    if path.is_file():
        if args.follow:
            raise _WrongCall("--follow needs a match id; a file does not change")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise _WrongCall(f"{args.source} is not JSON: {error}") from error
        game, events, names = from_export(data)
        _print_transcript(game, events, names, args)
        return 0
    try:
        match_id = UUID(args.source)
    except ValueError:
        raise _WrongCall(f"{args.source!r} is neither a file nor a match id") from None
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise _WrongCall("a match id needs DATABASE_URL, the database the match is stored in")
    pool = await connect(url)
    try:
        matches, log = MatchStore(pool), EventStore(pool)
        record = await matches.get(match_id)
        if record is None:
            raise _WrongCall(f"no match {match_id} in the database")
        if record.game not in RENDERERS:
            raise _WrongCall(f"no transcript for {record.game}")
        names = await matches.display_names(record)
        if not args.follow:
            _print_transcript(record.game, await log.load(match_id), names, args)
            return 0
        shown_as = argparse.Namespace(
            raw=False, lang=args.lang, no_spoilers=not args.spoilers, all=args.all
        )
        printer = _printer(record.game, names, shown_as)
        shown = 0
        while True:
            events = await log.load(match_id)
            await printer(shown, events[shown:])
            shown = len(events)
            current = await matches.get(match_id)
            if current is None or current.status != "running":
                if len(await log.load(match_id)) == shown:
                    return 0
                continue
            await asyncio.sleep(1.0)
    finally:
        await pool.close()


def _print_transcript(
    game: str, events: Sequence[Event], names: Any, args: argparse.Namespace
) -> None:
    lines = render_match(events, names, args.lang, args.spoilers, game=game)
    minimum = 1 if args.all else 2
    if args.format == "json":
        shown = [line for line in lines if line.importance >= minimum]
        print(json.dumps([line.model_dump() for line in shown], ensure_ascii=False, indent=1))
    elif args.format == "markdown":
        print(to_markdown(lines, minimum), end="")
    else:
        print(to_text(lines, minimum), end="")


if __name__ == "__main__":
    raise SystemExit(main())
