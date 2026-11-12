# D-114 · A garbled tool call that clearly means one move is repaired, and the move says so

- **Date:** 2026-11-11
- **Decision:** The runner reads a model's tool arguments kindly where that is
  safe (`arena/agents/arguments.py`): the first JSON object is taken out of
  text around it, keys the tool does not have are dropped, a tool without
  arguments takes `{}` whatever came with it, a number written as text
  becomes the number its schema wants, and a thought that is not text is
  dropped. Nothing is guessed: a value that is missing or wrong stays wrong,
  and the engine checks the result against the schema and the rules as
  before. Every repair is named on the move's `decision` event (`repairs`,
  with the raw call in `raw_arguments`), so a repaired move counts as valid
  but not clean. After 3 garbled answers in a match a model is offered its
  tools without the `thought` argument (`simple_schema` on the event); its
  thought is then the text beside the call. A call the engine still refuses
  is told exactly which fields the tool takes. All of this only with the match
  setting `answer_repair: "v1"`; the default `"off"` reads every call as sent,
  with the old correction text and no switch, so experiments stay comparable
  with matches played before. The engine keeps the setting from the game
  (`game_settings`) and records it in `match_started`; an unknown value is
  refused (422 at `POST /matches`). Experiment runs send it explicitly; the
  launch form offers `v1` for the owner's own matches.
- **Why:** In a heads-up Poker match 14 of gpt-luna's 66 answers were
  refused for the format of a call whose meaning was clear (reasoning text in
  the arguments, mojibake keys on `check`), and every refusal cost a
  correction round. The engine stays the only judge of a move; the runner
  only reads the format.
- **Alternatives:** Refusing every garbled call (costs time and money and
  looks like errors to viewers); repairing in the engine (it would judge the
  model's format, not the move); guessing mangled key names (a wrong guess
  plays a move the model did not mean).
