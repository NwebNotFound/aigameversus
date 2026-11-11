-- Which prompt the models of a match read (GamePlugin.prompt_version), so matches can be
-- filtered by it without reading their logs. NULL for matches recorded before this column.
ALTER TABLE matches ADD COLUMN prompt_version text;
