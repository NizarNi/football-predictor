# CONTRACT State of the Team (SoT)

## A. Status at a Glance
- Shipped once merged:
  - … T35a/b/c/d/e, T35f

## Phase 5 — UX & Perf Productionization
- T35f — Rolling xG + request memo + log de-noise — 🟡 active
  - Compute 5-match league-only rolling xG; memoize per request; reuse across `/match` xg|totals|btts; ensure BTTS falls back to the season cache when logs are thin. Collapse alias/xG INFO spam into single summaries; retain detailed DEBUG output.
