# D-109 · Seat ids in the players' own words are shown as name chips

- **Date:** 2026-11-11
- **Decision:** Prompts stay anonymous: players see seat ids, so models write
  "p2, two kings with your history?". In speech, whisper and thought bubbles,
  the web draws each such id as that seat's name chip: its avatar, colour and
  display name (`mentionParts`, `Mention.svelte`).
  - What a language glues to an id stays text after the chip ("p4s Frage",
    "p3's vote", "p4-Antwort", "p4:"); upper case and lists ("P4", "p1/p2") count too.
  - Only seats of the match count: "p9" in a four-seat match, or "top2",
    stays text.
  - A "Show raw words" switch in the commentary shows the words exactly as
    written. The stored text is never changed.
  - Captions and call-outs show the same names as plain text.
  - The replay list names seats by display name.
  - The naming fallback for arenas that send no `display` now follows the
    arena's rule (D-104): every seat of a repeated model is numbered, and a
    bot is "Bot <seat number>".
- **Why:** Nils could not tell whom a model meant by "p2". Rewriting the
  prompts would put model names in front of the models, which biases play and
  the research. So the ids stay, and only the viewer sees names.
- **Alternatives:** Model names in the prompts (bias); replacing the ids with
  plain names in the bubbles (it hides that the model wrote an id, and the
  chip shows whom it meant at a glance).
