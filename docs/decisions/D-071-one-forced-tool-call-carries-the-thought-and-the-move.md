# D-071 · One forced tool call carries the thought and the move; reasoning is kept short

- **Date:** 2026-11-11
- **Decision:** This replaces the answer format of the agent decision (text
  is the thought, the tool call is the move) for what goes to a model:
  - Every call is sent with `tool_choice: required`.
  - Every tool gets a first argument `thought`, added where the tools are
    described for the model (`tool_schemas`). The agent runner takes it out
    and logs it as the thought; a game never sees it, and a game tool with an
    argument of that name is refused. Text beside the call is still the
    thought when the argument is empty or missing.
  - Every call carries `reasoning_effort` from `limits.reasoning_effort` in
    `config/models.yaml`, set to `low`. When an answer has no text of its
    own, the model's reasoning is its text.
  - A reply knows whether it ran into the output limit (`ModelReply.cut_off`);
    such a reply without a tool call is told that it was cut off and to be
    brief. The output limit stays at 1500 tokens.
  - A request that a provider refuses (400, 404 or 422) while it carries
    these options is sent once more without them. Only if that is refused
    too does the seat lose its model. In a test of all eight roster models
    one refused the options outright, and another, served by several
    providers, took them in one match and refused them in the next.
    The budget has booked that call once, at its upper bound; the second
    request goes out under the same booking. That holds only because a
    refused request is not billed, so at most one of the two costs money.
    The set of statuses must therefore never grow to one a provider may bill.
- **Why:** Two real matches with the cheapest models of the roster. In the
  first (Liar's Deck, four models) 83 of 130 answers were rejected and 18
  turns went to the random fallback: two reasoning models spent the whole
  output limit thinking in 73 of 87 calls, and that thinking was 90 % of the
  output tokens paid for. With `reasoning_effort: low` (Poker, six models)
  those two were clean and calls were three times faster, but 30 of 138
  answers were still rejected: two other models answered in prose or wrote
  the call as text. Asking for text and a tool call in one answer is more
  than several of these models do; one call that holds both is what all of
  them can do, and it is one model call per move, which is also the cheapest.
- **Alternatives:** A higher output limit (pays for more of the same); a
  separate `think` tool as in the spec (a second call per move); thoughts
  only from models that write text beside a call (most cheap ones do not);
  parsing calls out of prose (guesswork per model); dropping the models that
  failed (they are among the cheapest).
