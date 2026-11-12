# D-116 · Throne of Tokens is played with one call per nation and round, and a broken order is dropped, not the call

- **Date:** 2026-11-12
- **Decision:** A round of Throne of Tokens is one simultaneous engine turn:
  every nation is asked once and answers with one `submit_orders` call that
  holds its orders, messages, offers and answers to offers; an offer can be
  answered in the next round and lapses after. There is no separate info or
  diplomacy phase: the observation carries what a nation may know. The
  engine refuses a call of the wrong shape, as in every game; an order that
  breaks a rule is dropped when it runs, with an `order_refused` event for
  that nation, and the other orders go on. The interfaces between the parts
  of the game are pinned in [docs/civ-interfaces.md](../civ-interfaces.md).
- **Why:** DESIGN.md's info calls and two diplomacy passes would cost three
  to ten calls per nation and round; one call keeps a 60-round match of six
  nations at 360 calls, which a cost cap can carry. A list of twenty orders
  is mostly right: refusing all of it for one mistake would cost a
  correction round each time and teach the model nothing the refusal note
  does not.
- **Alternatives:** The phases of DESIGN.md (better negotiation, several
  times the cost); one call per order (a hundred calls a round); refusing the
  whole call for any broken order (correction loops on long lists).
