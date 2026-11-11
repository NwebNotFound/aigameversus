-- Demo profiles (arena.ratings.demo_seed) are marked, so the leaderboard can hide them.
ALTER TABLE player_profiles ADD COLUMN is_demo boolean NOT NULL DEFAULT false;
UPDATE player_profiles SET is_demo = true WHERE name LIKE 'DEMO %' AND model_id = 'random-bot';
