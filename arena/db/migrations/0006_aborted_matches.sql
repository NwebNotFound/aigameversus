-- A spectator can abort a match: it stops where it is and keeps its log.
ALTER TABLE matches DROP CONSTRAINT matches_status_check;
ALTER TABLE matches ADD CONSTRAINT matches_status_check
    CHECK (status IN ('running', 'finished', 'failed', 'interrupted', 'aborted'));
