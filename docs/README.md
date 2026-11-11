# Documentation

Start with the [README](../README.md) in the repository root: what the project
is, a quick start and what is built.

| Document | What it is |
| --- | --- |
| [DESIGN.md](DESIGN.md) | The spec: vision, platform, the four games, UI, memory, costs, roadmap. In German. Where it differs from what was built, DECISIONS wins. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | The building blocks, one turn of a match, events and replay, the Compose services, and what is still planned. |
| [TESTING.md](TESTING.md) | How to run the tests, the linters, the secret scan and the Compose smoke test; Windows notes. |
| [DECISIONS.md](DECISIONS.md) | Every decision where the spec is open or overridden: date, decision, why, alternatives. Numbers `D-001` and up, ascending, never reused. |
| [CREDITS.md](CREDITS.md) | Where every asset and library comes from. |
| [images/](images/) | Screenshots and GIFs used in the README (made by `scripts/make_showcase.sh`). |

More, next to the code they describe:

- [../CLAUDE.md](../CLAUDE.md): conventions and "how to add a game, a role, a variant, a personality" for contributors, human or AI.
- [../games/werewolf/roles/README.md](../games/werewolf/roles/README.md): how to add a Werewolf role.
- [../games/civ/data/README.md](../games/civ/data/README.md): the Throne of Tokens data files.
- [../research/README.md](../research/README.md): how the models are evaluated: state, budget, build steps.
- [../experiments/README.md](../experiments/README.md): experiment plans, written before their first paid match, and their schedules.
