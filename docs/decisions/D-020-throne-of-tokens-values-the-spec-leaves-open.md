# D-020 · Throne of Tokens values the spec leaves open

- **Date:** 2026-11-11
- **Decision:** Starting values, all in the data files and meant to be tuned:
  - Event chance per round: plague 4 %, drought 3 % (food −50 %, radius 2,
    3 rounds), rebellion 5 % (only cities conquered within 10 rounds), barbarians
    5 % (2 spearmen, 1 swordsman), gold find 5 % (+25 gold), good harvest 6 %
    (+5 food).
  - Treaties: peace and alliance last until broken; non-aggression and open
    borders 3–30 rounds (default 10); tribute 1–20 (default 5). An alliance
    includes open borders.
  - Reputation starts at 50. Trade fee 10 %, +10 % below reputation 30.
  - Start stock 5 food, 5 wood, 0 iron, 5 gold, besides the capital and units.
  - City focus: growth → food, production → wood, military → iron.
  - Pillage yields 50 % of the building's cost. One of each building per city.
  - Divisions in the score and in building slots round down.
  - English ids: Reiter = `horseman`, Belagerung = `siege_engine`,
    Schmiede = `forge`, Speicher = `granary`.
- **Why:** The spec gives no number for these; these keep events rare enough
  not to decide a 60-round match on their own.
- **Alternatives:** leave them out until the systems need them (phase 7
  engine work would then block on data).
