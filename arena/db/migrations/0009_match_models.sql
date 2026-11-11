-- Which model played which seat of a match: seat -> model id from config/models.yaml.
-- NULL for a match of random bots.
ALTER TABLE matches ADD COLUMN models jsonb;
