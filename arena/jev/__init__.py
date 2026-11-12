"""Jev, a decision model that only repairs and tags; it never decides a move of its own.

- `client`: the typed client (`HttpJev`, refused unless ARENA_ALLOW_JEV=1) and `FakeJev`
  for tests. Every real call goes through `Budget.jev`, which books it in the ledger.
- `repair`: tier 2 of the move repair (answer_repair "v2"): which LEGAL move did the model
  mean with its broken call? Played only above a threshold, else the random fallback.
- `config`: `config/jev.yaml`.
"""
