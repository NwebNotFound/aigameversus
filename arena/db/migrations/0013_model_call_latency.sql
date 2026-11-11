-- How long a model call took (ms, from sending to the answer) and how many of its output
-- tokens went into thinking. NULL: not known (a call that failed, or an older row).
ALTER TABLE model_calls ADD COLUMN latency_ms integer;
ALTER TABLE model_calls ADD COLUMN reasoning_tokens integer;
