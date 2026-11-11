# Real models in the stack: key, ledger, backups

`docker compose up` plays random bots and holds no key. This page turns on
model seats in the stack. **Every model match then makes paid calls**, inside
the caps of [config/models.yaml](../config/models.yaml) (0.50 EUR per match,
25 EUR per calendar month by default).

## What the stack needs

| Piece | Why | Where |
| --- | --- | --- |
| Spend ledger | Every call is booked here before it is sent; the month cap is summed from it. It outlives the stack: `docker compose down -v` must not reset what the month has cost. | Postgres container `aigv-ledger`, not part of the Compose project |
| Key file | The provider key, read by the arena when a model match starts | A file outside the repository, mounted read-only |
| `docker-compose.models.yml` | Turns on `ARENA_ALLOW_MODEL_SEATS`, passes the ledger URL and mounts the key | This repository |

## Set up

1. **The ledger database**, once. Its volume is the record of what was spent:
   never delete it.

   ```bash
   docker run -d --name aigv-ledger --restart unless-stopped \
     -e POSTGRES_USER=arena -e POSTGRES_DB=arena -e POSTGRES_PASSWORD=<password> \
     -p 127.0.0.1:5435:5432 -v aigv-ledger:/var/lib/postgresql postgres:18-alpine
   ```

   The arena creates its tables at the first start. (The ledger of this
   project's first matches lives in an older volume named
   `aigameversus-builder-runs-pg`; the container was renamed, not recreated.)

2. **The key file**: a text file outside the repository that holds only the
   key, readable by you alone. The arena reads it at the start of every model
   match, so a replaced file counts from the next match; an empty or missing
   file means no key, and model seats are refused (503). On Linux the file
   must be readable by the container's user.

3. **`.env`** (gitignored) next to `docker-compose.yml`:

   ```bash
   OPENROUTER_API_KEY_PATH=/path/outside/the/repo/openrouter_api_key
   LEDGER_DATABASE_URL=postgresql://arena:<password>@host.docker.internal:5435/arena
   ```

4. **Start** with the override:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.models.yml up -d --build
   ```

   Compose refuses to start when either variable is missing. The arena starts
   without a reachable ledger, but then refuses model seats and every cost
   endpoint answers 503 until the ledger answers.

`arena run --models` reads the same `LEDGER_DATABASE_URL` from the
environment (default: `DATABASE_URL`), with `127.0.0.1:5435` instead of
`host.docker.internal`.

## Safety net

Before a model match starts, the arena (API and command) checks the ledger:

- It must answer. Otherwise: 503, nothing is recorded, sent or booked.
- It must not be empty while the match database holds finished matches with
  model seats. Each of those booked calls, so an empty ledger beside them is
  the wrong database or a lost one, and its month sum would be too low.

## Backups

`scripts/backup-ledger.sh [directory]` dumps the ledger database
(`pg_dump --format=custom`) into a directory outside the repository (default
`~/aigameversus-backups`, or `$ARENA_BACKUP_DIR`) and keeps the newest 30
dumps. Run it daily. On Windows, a scheduled task:

```powershell
schtasks /Create /TN "AIGameVersus ledger backup" /SC DAILY /ST 03:00 /TR "\"C:\Program Files\Git\bin\bash.exe\" -lc 'cd /c/path/to/aigameversus && scripts/backup-ledger.sh'"
```

On Linux or macOS, a cron line: `0 3 * * * cd /path/to/aigameversus && scripts/backup-ledger.sh`.

Restore into the running container:

```bash
docker exec -i aigv-ledger pg_restore -U arena -d arena --clean < ~/aigameversus-backups/ledger-<time>.dump
```

## The risk that stays

The API has no login and listens on 127.0.0.1 only. With
`docker-compose.models.yml`, **any program on this machine** that can reach
port 8100 can start model matches by sending `confirm_spend: true`. The caps
limit what that can cost (one match: 0.50 EUR, the month: 25 EUR), and every
call is in the ledger with its match. Start the stack with the override only
while real matches are wanted, and stop it, or start it without the override,
afterwards.
