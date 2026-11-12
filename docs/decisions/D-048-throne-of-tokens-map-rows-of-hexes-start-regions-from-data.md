# D-048 · Throne of Tokens map: rows of hexes, start regions from data, land in one piece

- **Date:** 2026-11-11
- **Decision:** The map is a rectangle of hex tiles, ten per row, with six,
  seven or eight rows for four, five or six nations (60 to 80 tiles, mountains
  and water included). A tile is `(col, row)` and odd rows sit half a tile to
  the right. The map is stored as rows of terrain ids plus one start per
  nation. The spec asks for fair starts and for every nation to be short of
  one resource; the generator does it like this:
  - Capitals are picked greedily, each as far as possible from those before
    it, and the most widely spread of 20 such picks is used. Start regions
    (the six tiles a capital works) never share a tile and are never cut off
    by the rim. Which seat gets which capital is shuffled.
  - The tiles around a capital come from `map.start_regions` in
    `balance.yaml`: one list per scarce resource, all with the same total
    yield (12), laid out in random order. The four shortages are dealt out in
    turn, so with four nations each is short of something different.
  - Every other tile is drawn from `map.terrain_weights`. A draw whose land is
    not one piece is thrown away and drawn again.
  - The two iron deposits and two gold veins go outside the start regions,
    where the nearest capital has the smallest lead over the second nearest
    and that one is close, and never side by side.
- **Why:** A rectangle in rows is what a browser draws and a model reads most
  easily, and rows of ids pass through JSON without depending on key order
  (D-044). Equal start regions make fairness something a test can check, not
  a matter of luck with the seed. Land in one piece means no nation is locked
  in and no tile is unreachable. Rare tiles between nations give them
  something to fight or trade over, which is what the spec wants iron for.
- **Alternatives:** A hexagon-shaped map (its sizes jump from 61 to 91
  tiles); mirrored maps (fair, but every match looks alike and the shortages
  could not differ); judging random starts by a score and redrawing (fairness
  only on average); rivers along tile edges (the spec lists river as a
  terrain with its own yield).
