# D-087 · Prompts have versions: a game's rules and summary per `prompt_version`

- **Date:** 2026-11-11
- **Decision:** Each game keeps its prompt text next to its plugin
  (`games/<game>/prompt.py`, `rules.md` for the first version, `rules_v2.md` for
  the second) and names versions `<game>-p1`, `<game>-p2`. The match setting
  `prompt_version` chooses one (an unknown one is refused when the match is
  created); the plugin reports it through `prompt_version(settings)`, so it can
  be recorded with the match. Version p2 has new rules text (rules in short, the
  tools with an example call each, how to play well, with the numbers a model
  would otherwise have to work out) and a short situation summary built from the
  observation alone (`situation_summary`), shown above the full data. Version p1
  is unchanged, so experiments can compare the two. The default stays p1 until a
  comparison says otherwise. The rules texts state the default stacks, blinds and
  similar numbers, so a match with other settings reads wrong numbers there.
- **Why:** A change of prompt changes how every model plays; without a version in
  the log nobody can tell which prompt produced a result. The summary only
  restates and computes from what the player already sees, so it cannot leak.
- **Alternatives:** one prompt that is edited in place (no comparison, old logs
  mean different things over time); summaries written by a model (costs money,
  varies from run to run).
