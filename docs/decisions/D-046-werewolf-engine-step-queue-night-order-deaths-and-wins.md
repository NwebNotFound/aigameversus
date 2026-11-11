# D-046 · Werewolf engine: step queue, night order, deaths and wins

- **Date:** 2026-11-11
- **Decision:**
  - The match is a queue of single-player steps (sequential turn mode): night
    actions sorted by the role files' `night_order` (seat order within one
    slot), one wolf step per pack member at slot 6, the day's speeches (two
    rounds, starting at a seeded position among the living) and one vote per
    living player in seat order, and death effects. `night_started`,
    `day_started` and `player_died` rebuild the queue in `apply_event`, and
    `step_done` (spectators only) ends a turn.
  - Abilities live in `games/werewolf/abilities.py`, keyed by the handler
    names in the role files. A role whose handlers are not implemented cannot
    be put in a match; the random template draws only from playable roles.
  - Wolves may chat twice per night (40 words each) before their vote; the
    victim is the most-voted target, on a tie the first of the tied targets
    voted for. The Witch sees the victim only on her turn and may heal and
    poison in the same night.
  - Day vote: the most votes are executed; abstentions do not count; a tie
    (or no votes) executes nobody. A vote reason is a public message.
  - A dead player's role is revealed to everyone.
  - The winner is checked after the morning and after the execution and their
    death effects: village when no pack member lives, wolves when the living
    pack is at least as big as everyone else, nobody when all are dead. The
    winning side shares rank 1, the rest the next rank.
  - A match still undecided after the 30th day ends without a winner
    (`game_over` with `reason: night_limit`). With that, `max_turns` (D-040)
    is a true bound: 30 × `cycle_turns(16)` = 9,660, where one night and day
    holds at most one role step, one wolf step and two wolf chats per player,
    the Prime Wolf's choice, one captain vote, two speeches, one vote and two
    death effects per player, each of them possibly with a lover chat.
  - Targets are JSON-schema enums of the legal players, so the engine rejects
    illegal targets and the random bot picks from them. No `think` tool, as
    in D-033; `render_spec` is a plain method.
- **Why:** One queue makes every phase, the night order and the death
  chains of later roles the same mechanism, and keeps replays exact.
- **Alternatives:** simultaneous night actions; a strict-majority day vote;
  hidden roles after death; a random tie-break for the pack.
