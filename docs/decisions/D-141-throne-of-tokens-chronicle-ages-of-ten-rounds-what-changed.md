# D-141 · Throne of Tokens chronicle: ages of ten rounds, what changed the map

- **Date:** 2026-11-12
- **Decision:** Throne of Tokens gets a chronicle on the same pipeline as Werewolf and Liar's
  Deck: a digest of facts (`arena/chronicle/civ.py`), the words per fact
  (`arena/chronicle/tell_civ.py`), and templates in four styles, English and German
  (`templates/civ.{en,de}.yaml`).
  - **Chapters:** a prologue (the nations and the round limit), one chapter per *age* of
    10 rounds (`AGE`), and an epilogue (how it was won, the standings with their scores).
  - **What an age tells:**
    - cities founded, one line per nation and age;
    - cities conquered, a fallen capital in its own words;
    - the two biggest battles of the age, those with at least 3 units lost on both sides
      together, with the losses of each side;
    - wars declared (and who joined);
    - treaties signed (a peace in its own words) and broken;
    - plague, drought, rebellion and barbarians;
    - the start of a nation's gold countdown;
    - one public quote.
  - **Left out:** moves, production, growth, buildings, trades and gold finds. They are in
    the analytics, not the story.
  - **At a glance:** the winner and how they won, the length, the turning point, the greatest
    conqueror and the keenest diplomat.
    - The turning point is the first fallen capital, else the biggest battle, else the first
      war.
  - **The neutral side** (barbarians and rebels) is one singular name, "the barbarian horde" /
    "die Barbarenhorde", so every verb agrees with it. A sentence that starts with it gets a
    capital letter (`tell_civ.finish`), for Civ only.
  - **German templates:** a nation stands only in the nominative or the accusative, so the
    feminine article of the neutral side never needs another case.
  - **The AI fact check (D-140):** Civ's units, buildings, treaties and resources, in English
    and German, are fact words. A retelling may not add them.
- **Why:** Lead asked for the Civ chronicle gap to be closed, and the narrator samples include a
  Civ match. A 60-round match told round by round would be 60 near-empty chapters. Most
  rounds only move armies and grow cities.
- **Alternatives:**
  - A chapter per round, as in Liar's Deck: unreadable at 60 rounds.
  - A chapter per war: many matches have no war at all.
  - Every battle: a barbarian skirmish of one unit each is noise.
  - "The barbarians" in the plural: English and German verbs would then need a plural form
    for that one subject.
