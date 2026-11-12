# D-133 · Throne of Tokens has one setting, rounds, for a shorter match

- **Date:** 2026-11-12
- **Decision:** `settings.rounds` (a whole number from 1 to the data's
  `round_limit.rounds`, 60) ends a match after that round: the round-limit
  victory is checked then (`victory.round_limit(state, data)`), the state keeps
  it (`CivState.round_limit`, from `initial_state`, so a replay rebuilds it from
  `match_started`), the observation's `rounds_total` and the board say it, and
  the rules' "After round 60," names it. Domination and the economic countdown
  are unchanged. Every other setting is refused.
- **Why:** The Researcher's pilot C1 plays 20 rounds, about a third of the cost of
  60, and `POST /matches/estimate` must price exactly that match before
  anything is spent. Above 60 the engine's turn limit (`max_turns`, one per
  round) would stop the match, so the data's limit is the most.
- **Alternatives:** A mod of `victory.yaml` per experiment (changes the game
  for every match on the server); a free number above 60 with a per-match turn
  limit (no experiment needs it yet); shortening the economic countdown with
  the match (not asked for; the countdown stays a separate rule).
