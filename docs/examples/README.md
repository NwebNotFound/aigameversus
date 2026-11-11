# Example matches

Three matches played by real models, as `arena run --models ... --save FILE`
wrote them. Each file has the game and its version, the seed and settings, which
model sat in which seat, the result, what each seat cost in millionths of a
euro, and every event of the match: private thoughts, hidden cards and roles
included, each with `visible_to` saying who could see it while it was played
(`null` everybody, a list those players, an empty list spectators only).

| File | Game | Seats | How it ended | Calls | Time | Cost |
| --- | --- | --- | --- | --- | --- | --- |
| `liars_deck.json` | Liar's Deck, base variant | glm-flash, deepseek-flash, llama-scout, gemini-flash-lite | glm-flash is the last one alive after 10 rounds | 33 | 2 min 41 s | 0.012 EUR |
| `poker.json` | Poker, 20 hands, blinds double every 5 | glm-flash, deepseek-flash, llama-scout, gemini-flash-lite, gpt-luna, claude-haiku | gemini-flash-lite has the most chips at the hand limit | 138 | 6 min 32 s | 0.054 EUR |
| `werewolf.json` | Werewolf, 8 players: 2 werewolves, seer, witch, hunter, 3 villagers | all eight models of the roster | the werewolves (deepseek-flash and gemini-flash-lite) win on day 2 | 66 | 8 min 24 s | 0.041 EUR |

The model names are the ids in [config/models.yaml](../../config/models.yaml).
All three were played on 2026-11-11 with the cost caps in force (0.50 EUR per
match).

What to know before reading them as a contest:

- They are single matches. One match says little about which model plays
  better.
- In `liars_deck.json` seat `p3` was played by the random bot: the provider
  refused the model's first request (`agent_failed` in the log). The arena
  has since learned to send such a request once more without the options the
  provider refused.
- `poker.json` was played before the answer format was changed to one forced
  tool call. 30 of its 138 answers were rejected and 5 turns went to the
  random fallback, nearly all of them on seat `p3`, whose model wrote its
  moves as prose.
- In `werewolf.json` 14 of 66 answers were rejected, half of them by the
  game's own limit on the length of a speech, and one turn went to the random
  fallback.

To rebuild the final state of a match from its file:

```python
import json
from arena.engine.replay import replay
from arena.engine.types import Event
from arena.games import load_games

saved = json.load(open("docs/examples/werewolf.json", encoding="utf-8"))
state = replay(load_games()[saved["game"]], [Event(**event) for event in saved["events"]])
```

`replay` refuses a file whose game has changed its `version` since: the file
then shows a match under older rules. `tests/test_examples.py` checks the
files against the current games.
