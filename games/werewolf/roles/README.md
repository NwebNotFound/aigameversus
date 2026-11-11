# Adding a werewolf role

1. Create `<id>.yaml` in this folder (or in `mods/`). The id is snake_case English and must match the file name.
2. Fields (checked by `role.schema.json`):
   - `id`, `name` (German display name), `team` (`village`, `wolves` or `solo`)
   - `unique`: `true` if the role may appear at most once
   - `weight`: integer balance value (village-favouring positive, wolf-favouring negative)
   - `night_order`: integer position in the night (lower acts first) or `null` if the role does not act at night
   - `first_night_only`: optional, `true` for roles that act only on night 1
   - `hooks`: map of hook name to handler name, e.g. `on_morning: bear_growl`. Handler logic lives in code, not in YAML.
   - `description`: English rules text
   - `rules_snippet`: 1-3 sentences addressed to the player, put into the prompt only when the role is in play
3. Run `uv run pytest games/werewolf`.

Night order: 1 cupid, 2 wild_child, 3 protector, 4 seer, 5 little_girl, 6 wolves (werewolf, prime_wolf), 7 white_wolf (every second night), 8 witch, 9 raven.
The captain is an office, not a role; see `../options.yaml`.
