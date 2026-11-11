-- Who sat on each seat, for people to read: {"p1": {"name", "model_id", "kind"}}.
-- NULL for matches recorded before. `origin` says whether this server played the
-- match or a replay file brought it in.
ALTER TABLE matches ADD COLUMN seats jsonb;
ALTER TABLE matches ADD COLUMN origin text NOT NULL DEFAULT 'played'
    CHECK (origin IN ('played', 'imported'));
