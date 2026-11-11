# D-076 · The monthly cap is 25 euros

- **Date:** 2026-11-11
- **Decision:** `limits.month_eur` in `config/models.yaml` is 25.00 (it was
  5.00, D-001). The cap per match stays 0.50 EUR. Whatever is above 25 EUR a
  month still pauses a match, as before.
- **Why:** The project owner set it after the first real matches (six
  matches, 0.18 EUR together): he wants stronger models and research runs,
  which a 5 EUR month would stop early. He kept the per-match cap; a single
  research run may get a larger budget only when that is set for the run
  (a per-run budget is still to be built).
- **Alternatives:** No monthly cap (one runaway batch could spend without
  limit); a higher cap per match for everyone (a mistake would cost more).
