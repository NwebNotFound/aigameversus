"""The `arena` command: play a match in this process and print its event log.

It needs no server and no database, and it costs nothing: every seat is a
random bot.
"""

import argparse
import asyncio
import json
import random
import sys
from collections.abc import Sequence
from typing import Any

from arena.agents.random_bot import random_bots
from arena.engine.match import Match
from arena.engine.types import Event
from arena.games import load_games


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arena", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("games", help="list the games that can be played")
    run = commands.add_parser("run", help="play one match and print every event")
    run.add_argument("--game", required=True, help="id of the game, see `arena games`")
    run.add_argument(
        "--bots",
        action="store_true",
        required=True,
        help="fill every seat with a random bot (the only players this command offers so far)",
    )
    run.add_argument("--players", type=int, help="number of seats (default: the game's minimum)")
    run.add_argument("--seed", type=int, help="seed of the match (default: a random one)")
    run.add_argument(
        "--setting",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="a game setting; the value is read as JSON, or as text if it is not JSON",
    )
    args = parser.parse_args(argv)

    # Event data can hold any character; a console that cannot show one must not stop a match.
    sys.stdout.reconfigure(errors="backslashreplace")
    games = load_games()
    if args.command == "games":
        for game in games.values():
            print(f"{game.id:<12} {game.name} ({game.min_players} to {game.max_players} players)")
        return 0

    if args.game not in games:
        parser.error(f"unknown game {args.game!r}; choose from: {', '.join(games)}")
    plugin = games[args.game]
    players = [f"p{seat}" for seat in range(1, (args.players or plugin.min_players) + 1)]
    seed = random.SystemRandom().randrange(2**31) if args.seed is None else args.seed
    try:
        match = Match(
            plugin,
            random_bots(plugin, players, seed),
            seed=seed,
            settings=_settings(args.setting),
            sink=_print_events,
        )
    except ValueError as error:
        parser.error(str(error))
    print(f"{plugin.name} ({plugin.id}), players {' '.join(players)}, seed {seed}")
    placements = asyncio.run(match.run())
    ranking = sorted(placements, key=lambda placement: placement.rank)
    print("Result: " + "  ".join(f"{placement.rank}. {placement.player}" for placement in ranking))
    return 0


def _settings(pairs: Sequence[str]) -> dict[str, Any]:
    settings = {}
    for pair in pairs:
        name, separator, value = pair.partition("=")
        if not separator:
            raise ValueError(f"--setting needs NAME=VALUE, got {pair!r}")
        try:
            settings[name] = json.loads(value)
        except ValueError:
            settings[name] = value
    return settings


async def _print_events(first_seq: int, events: Sequence[Event]) -> None:
    """Print the events of one turn, one line each: position, type, data, who may see it."""
    for seq, event in enumerate(events, start=first_seq):
        if event.visible_to is None:
            audience = ""
        elif event.visible_to:
            audience = f"  [only {', '.join(event.visible_to)}]"
        else:
            audience = "  [spectators only]"
        data = json.dumps(event.data, ensure_ascii=False)
        print(f"{seq:>4}  {event.type:<16} {data}{audience}")


if __name__ == "__main__":
    raise SystemExit(main())
