# D-014 · asyncpg and SQL migration files, no ORM

- **Date:** 2026-11-11
- **Decision:** Postgres access uses asyncpg with plain SQL. Schema changes are
  numbered `.sql` files in `arena/db/migrations/`, applied in order inside one
  transaction and recorded in `schema_migrations`; an advisory lock keeps two
  processes from migrating at once. The arena applies them at startup.
- **Why:** The data model is an append-only event table plus a few lookup
  tables later; SQL says that more directly than an ORM mapping. The engine is
  async, so the driver is too. A migration runner of thirty lines is easier to
  read than an Alembic setup for forward-only migrations.
- **Alternatives:** SQLAlchemy with Alembic; psycopg 3 (its async mode needs a
  different event loop on Windows).
