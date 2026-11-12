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
  - **Spoiler-free:** the web server's allowlist drops `fog`, the stocks and the unit lists (`web/src/lib/server/redact.ts`), so the switch and the stock are not shown.
- **Why:** Civ is a top priority (Lead, 2026-11-12) and the interface doc is pinned (#122). Building against it now means the board is ready when the plugin lands (7.6). A realistic map from the real generator (`fixture-hex-map.json`) stands in until then.
- **Alternatives:** A canvas map: rejected, because it has no DOM for tests and no titles for screen readers. Square tiles: they don't fit the generator's hex geometry. Fog always on: the spectator view is meant to see everything; fog is a lens, not the default.
