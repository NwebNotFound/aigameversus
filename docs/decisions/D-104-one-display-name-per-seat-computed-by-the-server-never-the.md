# D-104 · One display name per seat, computed by the server, never the seat id

- **Date:** 2026-11-11
- **Decision:** The name shown for a seat is made once, in `display_names`
  (`arena/transcript/common.py`), and used in every line of the transcript (English and
  German), in `arena transcript`, in `arena run`, and handed to the UI as
  `players[seat].display`. A model is shown by its short name (`name` in
  `config/models.yaml`, else its id), numbered `gpt-luna #1`, `gpt-luna #2` when the same
  model sits more than once; a bot is `Bot 3`, with the number of its seat. The names are
  unique within a match. The seat id (`p3`) is a separate field `players[seat].seat`, for a
  small badge. The names come from the match record's seats (known from the first turn of
  a running match); a match recorded before seats were kept falls back to its profile
  labels, else the seat id.
- **Why:** People could not tell which seat was which model: the board said `p3`, the
  commentary `p1 plays 1 card`, the bubbles `p2`. A name made in one place cannot differ
  between the board, the commentary and the bubbles.
- **Alternatives:** each page building its own label (they drifted apart); the seat id as
  the name with the model in brackets (`p1 (glm-flash)`, what the lines said before: long,
  and still led with the number); suffixing only the second seat of a repeated model (the
  first and the second then look different for no reason).
