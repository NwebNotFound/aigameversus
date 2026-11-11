# D-049 · Fog of war: a nation sees what is in range now, by distance alone

- **Date:** 2026-11-11
- **Decision:** A nation sees the tiles within the radius of each of its
  viewpoints (cities and armies; 2 by default, more with a watchtower or a
  scout). Sight is plain distance: mountains and forests do not block it.
  `map_view` gives the terrain of those tiles and `None` for all others. No
  memory of tiles seen earlier is kept.
- **Why:** This is the rule as the spec states it, and it is the smallest
  one: the view is a function of the current state, so nothing about it has
  to be stored or replayed. The systems that own cities and armies pass their
  viewpoints with the radius each has.
- **Alternatives:** Remembering explored terrain (needs state per nation;
  can be added in the turn flow, step 7.6, if matches show that models lose
  their way); line of sight (more rules for models to hold in mind, little
  gain on a map this small).
