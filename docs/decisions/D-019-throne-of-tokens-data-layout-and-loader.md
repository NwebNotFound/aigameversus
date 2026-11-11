# D-019 · Throne of Tokens data: layout and loader

- **Date:** 2026-11-11
- **Decision:** Content lives in `games/civ/data/` (events in
  `games/civ/data/events/`, not `games/civ/events/` as one spec line says, to
  match the repo layout in the same spec). Lists are YAML lists of entries with
  an `id`, so duplicates are caught (YAML mappings silently drop duplicate
  keys). One event per file, file name = id. Pydantic models in
  `games/civ/data_loader.py` are the single source of the schema; the
  `*.schema.json` files are generated from them and a test fails when they are
  stale. Building-slot numbers sit in `balance.yaml` only, not also in
  `buildings.yaml`.
- **Why:** One place for each number; readable errors; editor validation for
  free.
- **Alternatives:** hand-written JSON schemas validated with `jsonschema`;
  one file per unit and building; id-keyed mappings.
