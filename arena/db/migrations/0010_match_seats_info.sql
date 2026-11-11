-- Who sat in each seat of a match, for people who watch it: seat -> {name, model_id, kind}.
-- NULL for matches recorded before this column existed.
ALTER TABLE matches ADD COLUMN seats jsonb;
-- Whether the match was played here or imported from a saved file.
ALTER TABLE matches ADD COLUMN origin text NOT NULL DEFAULT 'played'
    CHECK (origin IN ('played', 'imported'));
