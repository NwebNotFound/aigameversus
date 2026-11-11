# D-068 · The Poker spectator spec carries side pots and win chances

- **Date:** 2026-11-11
- **Decision:** `Poker.render_spec` adds `side_pots` (the main pot and side pots as
  `{amount, eligible}`, empty when fewer than two players are live) and, per
  seat, `win_probability`: the player's chance to win if the hand ran to the
  river now (`win_probabilities` of `games/poker/evaluator.py`, 400 sampled
  runouts, `None` for folded players). The random stream is fixed by hand number
  and board size, so a state always gives the same numbers. The Poker table
  shows the chances only with spoilers on, and `win_probability` joins the
  fields the UI hides with spoilers off.
- **Why:** The table must show pot and side pots and, optionally, the chances;
  the UI cannot evaluate hands. The chances follow from every hole card, so they
  are spectator information like the hole cards themselves.
- **Alternatives:** a hand evaluator in TypeScript (a second implementation to
  keep in step); a separate API endpoint for the chances (a second request per
  turn); exact enumeration (too slow before the flop).
