# D-124 · The Throne of Tokens board draws the hex map in SVG, with a nation's fog on request

- **Date:** 2026-11-12
- **Decision:** The `hex_map` render_spec of docs/civ-interfaces.md is drawn as one SVG:
  - **Tiles:** pointy-top hexagons, odd rows shifted half a tile as in `games/civ/world.py`. Each terrain has a fill and a small hand-drawn mark (trees, hills, peaks with snow, waves, a river line, an iron diamond, a gold coin, grass), so the map reads without colour too.
  - **Cities:** a crest in the owner's colour with the population, a dashed ring for walls, a star for a capital.
  - **Armies:** a banner with the strength, with a small shield when fortified; several armies on one tile stand side by side.
  - **This round's battles and wars:** battles are a flare outlined in the winner's colour; each war is a dashed red line between the two capitals.
  - **Nations panel:** colour, cities, reputation bar, stock (spectator view only) and wars; then treaties and a terrain legend.
  - **Colours:** nations take a fixed palette in `nations` order (blue, orange, purple, teal, then rose and ochre), chosen to stay apart in the dark theme and for the common colour blindnesses; neutral is slate.
  - **Fog:** in the spectator view a "Map as seen by" switch dims the tiles a nation does not see this round and hides cities, armies and battles there.
  - **Spoiler-free:** the map is one nation's (docs/civ-interfaces.md). The viewer picks the nation with `?nation=`, and the first nation is the default. The web server builds that view from the full board (`hexNationView` in `web/src/lib/server/redact.ts`):
    - the land;
    - only the cities, armies and battles on tiles in that nation's fog row (its own always), with the public fields;
    - unit lists and stock for its own only;
    - its fog row and no other.
    The page shows a "Map as seen by" switch that asks the server for another nation's map; the spectator lens is unchanged. When the plugin's `render_spec_for(state, nation)` exists (7.6), the server can ask the arena for it instead. The web filter mirrors the same list, so nothing changes for the viewer.
- **Why:** Civ is a top priority (Lead, 2026-11-12) and the interface doc is pinned (#122). Building against it now means the board is ready when the plugin lands (7.6). A realistic map from the real generator (`fixture-hex-map.json`) stands in until then.
- **Alternatives:** A canvas map: rejected, because it has no DOM for tests and no titles for screen readers. Square tiles: they don't fit the generator's hex geometry. Fog always on in the spectator view: it is meant to see everything; there the fog is a lens. A whole-map spoiler-free view (the first version of this PR): it would show every city and army, which no nation sees.
