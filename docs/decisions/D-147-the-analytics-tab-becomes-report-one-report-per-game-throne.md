# D-147 · The Analytics tab becomes Report, one report per game; Throne of Tokens gets its own from civ/1

- **Date:** 2026-11-12
- **Decision:** The match tab "Analytics" is called "Report" (design review, Shared/AIGameVersus/design/DESIGN-REVIEW.md, section 5).
  - **Loader:** `AnalyticsPanel` loads `GET /matches/{id}/analytics` and picks the report by the answer: a Civ answer (`isCiv`, `civ/1`) goes to `CivReport`; Liar's Deck keeps its charts (`hasNumbers`); any other game says its report is coming.
  - **Civ Report, first cards** (review 5.1, cards 0, 1 and 12):
    - the verdict as one sentence, with six numbers: battles, treaties, wars and betrayals, dropped orders as a share with its n, cut-off answers with their n, and cost;
    - "Who was ahead, and when did it turn?": score per nation over the rounds, each in its player slot colour and dash with end labels, war and conquest markers, and the lead-change answer;
    - "What did each seat cost, and what did it buy?": score, mean response, tokens, cut off, refused, bot moves, cost and cost per point.
  - **Spoiler-free:** the per-round parts are null, so the report shows the verdict, the public counts and a card that says what is hidden.
  - **Later:** the other cards follow with the chart kit (step 3).
- **Why:** Nils: "Civ analysis isn't working". The API answered, but the web discarded every answer that was not Liar's Deck. The review sets answer-first cards with questions as titles.
- **Alternatives:**
  - A separate Civ tab: one tab per game would split the same idea.
  - Keeping the name "Analytics": the review renames it for all games, since a report answers questions and does not list numbers.
