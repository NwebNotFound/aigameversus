# D-053 · Per-game statistics are pure functions over the event log

- **Date:** 2026-11-11
- **Decision:** Statistics live in `arena/stats/<game>.py` as pure functions
  from the stored event log of one match to a Pydantic model per player
  (`match_stats`), plus `aggregate` over many matches of one player. They read
  only events the plugin already emits. The first one is Liar's Deck: lie rate
  (lies / plays, a lie is a play with a card that is neither the table card nor a
  joker), times caught lying, success rate of "Liar!" calls (only calls the
  player chose to make; automatic calls are forced), rounds survived (rounds
  played minus the round of the fall) and the boldest bluff (the highest
  revolver risk, live chambers left / chambers left, faced while lying).
- **Why:** Computing from the log keeps the numbers reproducible and needs no
  change to a plugin. The helpers in `arena/ratings/stats.py` do the rates, so
  "no data" is `None`, never 0.
- **Alternatives:** counting in the plugin state (changes the plugins, and old
  logs would have no numbers); storing the numbers per match in a table.
