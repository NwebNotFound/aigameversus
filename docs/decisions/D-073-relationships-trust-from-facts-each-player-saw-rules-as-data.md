# D-073 · Relationships: trust from facts each player saw, rules as data

- **Date:** 2026-11-11
- **Decision:**
  - After a rated match the server adds its facts to the relationships of the
    seated profiles (`relationships`, `remembered_matches`, migration `0008`),
    once per match id, in one transaction. A memory problem never fails the
    match or its rating.
  - A fact is one player's view of another (`arena/memory/facts.py`) and is
    read only from the game events that player could see: public ones and
    those sent to them. Thoughts and spectator-only events are never read.
  - Facts today: Liar's Deck: caught lying, accused me falsely, told the truth
    when I called; Poker: bet or raised and lost every pot of the showdown (the
    stats' bluff rule); Werewolf: packmate, turned out to be a wolf (the seer's
    check, or the role shown at death; once per wolf), voted against me, voted
    against me though we were lovers.
  - What each fact is worth and its note are in `config/memory/trust.yaml`.
    A match sums its facts per pair, then trust is clamped to -100..+100.
    A pair keeps its 10 newest notes, newest first.
  - `GET /profiles/{id}/relations` lists the others, strongest feeling
    first; the profile page shows them as a trust list. `relations` left the
    profile response.
- **Why:** Facts from the observer's own view cannot leak hidden roles or
  cards. Rules as data can be tuned without code, as rule 7 asks.
- **Alternatives:** trust from the whole log (the seer's checks would reach
  every player); decay over time (not in the spec); notes for every match
  without a cap.
