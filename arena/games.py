"""Finds the games: every package under `games/` with a `plugin` module is one."""

import importlib
import importlib.util
import pkgutil

import games
from arena.engine.plugin import GamePlugin


def load_games() -> dict[str, GamePlugin]:
    """One plugin object per game, keyed by game id, in alphabetical order.

    A game is a folder `games/<id>/` whose `plugin.py` defines exactly one
    GamePlugin class with that `id`. Raises RuntimeError for a folder that
    breaks this rule: a game that cannot be found by its folder name must not
    start half-working.
    """
    found = {}
    for package in sorted(pkgutil.iter_modules(games.__path__), key=lambda module: module.name):
        name = f"games.{package.name}.plugin"
        if not package.ispkg or importlib.util.find_spec(name) is None:
            continue  # data and helpers of a game whose plugin is not written yet
        module = importlib.import_module(name)
        plugins = [
            value
            for value in vars(module).values()
            if isinstance(value, type)
            and issubclass(value, GamePlugin)
            and value.__module__ == module.__name__
        ]
        if len(plugins) != 1:
            raise RuntimeError(f"{name} must define exactly one GamePlugin, found {len(plugins)}")
        if plugins[0].id != package.name:
            raise RuntimeError(
                f"{name}: the plugin id {plugins[0].id!r} must be the folder name {package.name!r}"
            )
        found[package.name] = plugins[0]()
    return found
