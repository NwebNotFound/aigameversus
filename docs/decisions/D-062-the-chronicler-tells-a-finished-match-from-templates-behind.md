# D-062 · The chronicler tells a finished match from templates, behind a Narrator

- **Date:** 2026-11-11
- **Decision:** `arena/chronicle/` builds a chapter-by-chapter story from the
  stored event log of a finished match of Liar's Deck, Poker or Werewolf:
  chapters are rounds, hands and nights, made of beats (a caught lie, a shot,
  an all-in, a death, a vote, the win). `tell(events, style=, lang=, names=)`
  gives a `Chronicle`; `to_markdown` exports it; `GET /matches/{id}/chronicle?
  style=&lang=&format=` serves it. The four styles (epic, news, sports, novel)
  in English and German are fixed templates, so the same log gives the same
  text and nothing is paid. `Narrator` is the interface a model can implement
  later to retell a chapter from its beats; the default `TemplateNarrator`
  needs no model. The story uses spectator information (hidden cards, roles),
  so a log without `match_finished` is refused, and the endpoint answers 409
  for a match that is still running.
- **Why:** A story told during the match would reveal what players may not
  know, and the templates keep tests exact and the cost at zero. Beats keep the
  facts apart from the words, which is what a model narrator needs.
- **Alternatives:** telling the story live from public events only (much
  thinner, and the replay page can use the finished one); one free-text
  generator without beats (not testable).
