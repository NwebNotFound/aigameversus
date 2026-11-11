-- Which batch a match belongs to (an experiment stage, a league): {"id", "label", "index", "of"}.
-- NULL for a match played on its own and for matches recorded before this column.
ALTER TABLE matches ADD COLUMN batch jsonb;
CREATE INDEX matches_batch_id ON matches ((batch->>'id')) WHERE batch IS NOT NULL;
