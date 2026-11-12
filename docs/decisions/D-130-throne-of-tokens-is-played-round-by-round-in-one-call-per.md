# D-130 · Throne of Tokens is played round by round in one call per nation

- **Date:** 2026-11-12
- **Decision:** The plugin (`games/civ/plugin.py`) plays one round per engine
  turn, all nations at once, and fills in what docs/civ-interfaces.md leaves
  to the turn flow:
  - The plugin opens a round (start, lapsed offers, finished buildings),
    asks every nation on that open state, then closes it (orders,
    barbarians, combat, trades, production, upkeep, growth, events,
    weariness, victory) and opens the next in the same turn. A nation is
    always asked on an open round, so "moved this round" and the offers to
    answer are right in its observation.
  - `submit_orders` has one flat order object with every field an order may
    have and a `type`; what a type needs is checked when it runs. A missing
    field or a broken rule drops that order (`order_refused`, private), never
    the call.
  - Orders run type by type (diplomacy, cities, armies) and within a type in
    seat order. A `move` onto a tile another nation holds is an attack when
    at war (or on barbarians) and refused otherwise.
  - Barbarians (neutral armies) attack the nearest held tile in reach, else
    walk one step's reach towards the nearest city; no random draw.
  - The plan is cut to its first 60 words; it is kept per nation and shown
    back only to it (`plan_set`, private). It and a refused order (which may
    carry a message's text) are the only places outside `message` where a
    model's words are stored, and both reach only their own author: no model
    reads another model's words except as a `message`.
  - Messages and the events of the last round reach a model as the prompt's
    events (marked as player content), not as observation fields: a model's
    text never sits inside the observation's JSON.
  - The scoreboard (D-128) is built by the plugin from the state alone and
    added to every observation.
  - A nation without cities and armies is out: it is not asked again and
    ranks by its score.
- **Why:** One call per nation and round is the cost model of the interface
  doc (360 calls for 60 rounds of six). Opening the next round right after
  closing one keeps the observation and the rules on the same round number
  without a phase field in the state. A flat schema keeps the tool short in
  every prompt, and checking fields per order keeps a list of twenty orders
  from failing for one typo.
- **Alternatives:** A `oneOf` schema per order type (exact, but several
  times longer in every call, and one bad order makes the engine refuse the
  whole call); begin the round in `apply_actions` (the observation would
  show last round's moves as this round's); messages copied into the
  observation (another model's words inside the game data).
