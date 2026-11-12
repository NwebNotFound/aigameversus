# D-142 · Poker chronicle: a chapter per blind level; the old beats path removed

- **Date:** 2026-11-12
- **Decision:** Poker moves to the digest → template pipeline of the other games
  (`arena/chronicle/poker.py`, `tell_poker.py`, `templates/poker.{en,de}.yaml`, four styles).
  The old path goes: `beats.py`, the `TEXT`/`MORE` templates, `Narrator`/`TemplateNarrator`
  and the `narrator` argument of `tell`. Poker was its last user.
  `text.py` keeps `STYLES`, `LANGS` and the Werewolf `CAUSES` that the transcript and the
  analytics share.
  - **Chapters:** a prologue (players, starting stack, hand limit), one chapter per **blind
    level** (the blinds double every `double_every` hands, 10 by default), and an epilogue
    (the winner, or the chip leader at the hand limit, and the final order).
  - **What a level tells:**
    - the blinds and the players left. The first level says what the blinds start at, not
      that they rose;
    - the two biggest pots of at least 10 big blinds;
    - the busts, with their place;
    - one public quote.
  - **What a pot tells:**
    - after a showdown, the winning hand and the best losing hand;
    - who was all in;
    - a split;
    - otherwise "won without a showdown".
    - It is a **bluff** when the winner bet or raised and held no pair with the board as it
      lay (the flop at least). The hole cards are in the spectator log.
  - **Uncalled bets:** a pot only one player could win counts only if the hand has no
    contested pot. Next to contested pots it is an uncalled bet coming back, not a win.
  - **At a glance:** the winner or chip leader, the length in hands, the biggest pot, the best
    hand shown (two pair or better), and the boldest raiser (at least 3 raises and all-ins).
  - **Hand names** follow "with" in English ("with a flush") and "mit" in German, in the
    dative ("mit einem Flush"). The templates use them only that way.
  - **Key moments** name each player once (`compose.key_moments`).
- **Why:**
  - Lead asked for the Poker chronicle gap to be closed, and the narrator samples include a
    Poker match.
  - The old chronicle told every hand as a chapter, street by street. At up to 100 hands
    that is a log, not a story.
  - The rule is no dead code. Once Poker moved, nothing else used the beats path. D-140's
    `arena/chronicle/ai.py` is the model's way in now, replacing the old `Narrator` seam.
- **Alternatives:**
  - A chapter per hand, as before.
  - A chapter per 10 hands whatever the blinds. The blind level is what changes the game,
    and the settings already define it.
  - Keeping the beats path for Poker alongside: two template systems to maintain.
