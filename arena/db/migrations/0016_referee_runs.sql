-- Jev step 3 (D-134): the post-match referee of a finished match, at most one run per match.
-- Research tags, unvalidated until people label the same moments; spoiler-rich: the API
-- shows them with spoilers only. The call itself is in model_calls under the match id.
CREATE TABLE referee_runs (
    match_id      uuid        PRIMARY KEY REFERENCES matches (id),
    created_at    timestamptz NOT NULL,
    status        text        NOT NULL,   -- done, failed
    reason        text,                   -- why it failed (a Jev error kind), if it did
    rubric        text        NOT NULL,   -- the version of the questions asked
    selection     jsonb       NOT NULL,   -- the chosen moments, the counts per category
    questions     jsonb       NOT NULL,   -- exactly what Jev was asked
    tags          jsonb       NOT NULL DEFAULT '[]'  -- per moment: the raw distributions
);
