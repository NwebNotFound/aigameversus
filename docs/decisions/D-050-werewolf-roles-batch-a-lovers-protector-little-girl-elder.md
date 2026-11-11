# D-050 · Werewolf roles batch A: lovers, Protector, Little Girl, Elder, Idiot, Scapegoat

- **Date:** 2026-11-11
- **Decision:**
  - Cupid links two different living players on night 1 (himself allowed).
    Only Cupid sees the link event; the lovers learn each other. A lover's
    death kills the other at once ("grief"), through every death path.
    Lovers may `lover_chat` (40 words, lovers only) once in any of their
    turns without ending it. Lovers from both sides (one in the pack, one
    not) win alone when they are the last two alive, and count for neither
    side's win.
  - The Protector protects one living player a night (himself allowed), never
    the same one twice in a row. Protection stops the wolves' kill, not the
    Witch's poison.
  - The Little Girl may `spy` or `stay_in_bed`. Spying rolls twice from the
    match seed: 30 % she learns one random living wolf (private), 15 % she is
    caught (spectators only) and then becomes the wolves' victim in place of
    theirs. The Protector and the Witch can still save her.
  - The Elder survives the first wolf attack (he alone learns it). If the
    village executes him, every village-team role loses its powers for the
    rest of the match: their night steps and passive hooks stop, except a
    lover's grief.
  - An executed Village Idiot survives, is revealed, and no longer votes.
  - On a real tie (two or more top targets with votes) a living Scapegoat
    dies instead of nobody; no votes at all is not a tie.
- **Why:** The spec's role texts leave these open; each rule keeps one clear
  answer per case and fits the existing step queue and death chain.
- **Alternatives:** lovers win with their teams; protection against poison;
  wolves informed when they catch the girl; the Elder surviving poison.
