# Cross-Audit Remediation Backlog

This backlog aligns remediation work across three independent assessments:

## Implementation Progress

- ✅ Deterministic match identifiers now flow from Odds API event IDs (Priority 0).
- ✅ Bookmaker outcomes are normalized via shared utilities before aggregation (Priority 0).
- ✅ Bare `except` blocks were replaced with explicit exception handling across match data pipelines (Priority 0).
- ✅ Structured logging and unified JSON error helpers back the Flask surface, removing ad-hoc prints (Priority 1).
- ✅ Odds API key rotation is guarded by thread locks with persisted invalid-key state (Priority 1).

1. **Reliability & Data Integrity Audit** – internal deep dive captured in `AUDIT.md` that surfaced unstable match IDs, fragile bookmaker aggregation, and thread-unsafe API key rotation.【F:AUDIT.md†L9-L33】
2. **External Static Scan** – automated code heuristics highlighting bare `except` blocks, direct network usage, and other risk hotspots in the Flask app and data clients.【F:attached_assets/external_audits.md†L3-L10】
3. **External Architecture & Quality Review** – manual audit recommending stronger error handling, consolidated configuration, richer logging, persistent caching, and broader test coverage.【F:attached_assets/external_audits.md†L12-L20】

Priorities use a 0–2 scale (0 = immediate blocker, 1 = next sprint, 2 = strategic backlog). Suggested owners map to existing functional teams.

## Priority 0 – Immediate Reliability Fixes

| Action | Audits | Target Outcome | Owner |
| --- | --- | --- | --- |
| Replace `hash()`-derived match identifiers with a deterministic value tied to the provider `event_id` (UUID5/SHA-256) and propagate to all consumers. | Reliability, Architecture | Stable permalinks and log correlation for upcoming/predict endpoints. | Backend |
| Normalize bookmaker outcome names before aggregation (casefold, accent strip, reuse `normalize_team_name`, fallback to `fuzzy_team_match`). | Reliability | Accurate market probabilities with no silent 0.33 defaults. | Backend |
| Remove bare `except:` blocks in request and data pipelines (`app.py`, `xg_data_fetcher.py`) by catching explicit exception classes and logging context. | Static Scan, Architecture | Transparent failure modes that support debugging and alerting. | Backend |

## Priority 1 – Next Sprint Hardening

| Action | Audits | Target Outcome | Owner |
| --- | --- | --- | --- |
| Guard Odds API key rotation with a threading lock and persist invalid keys across restarts; emit structured warnings when keys are exhausted. | Reliability, Security | Thread-safe key usage with observable key health. | Backend |
| Extract shared Odds API retrieval logic for `/upcoming` and `/search`, standardize JSON error responses, and move `next_n_days` defaults into `config.py`. | Architecture | Consistent endpoints with reusable data pipelines and configurable horizons. | Backend |
| Move league/market configuration (regions, markets, league codes) out of `odds_api_client.py` into `config.py` and document rotation cadence. | Architecture, Security | Centralized configuration without code changes for market tweaks. | Platform Engineering |
| Persist high-value caches (Elo, xG, Understat standings) using a shared backend (Redis/Memcached) with TTLs aligned to source refresh rates. | Architecture, Observability | Faster responses with predictable data freshness across deploys. | DevOps |
| Replace ad-hoc `print()` statements with structured application logging and sanitize all outbound error payloads via a shared helper. | Architecture, Observability | Consistent redaction and searchable logs for incident response. | Backend |
| Establish automated regression tests covering odds normalization, API error handling, and caching fallbacks; integrate into CI. | Reliability, Architecture | Prevent regressions on key data integrity paths. | QA |
| Stand up a minimal CI loop (e.g., GitHub Actions) that runs unit tests, linting, and security scans on every PR/merge. | Reliability, Architecture | Enforce remediation guardrails and surface regressions before deploy. | DevOps |

## Priority 2 – Strategic Enhancements

| Action | Audits | Target Outcome | Owner |
| --- | --- | --- | --- |
| Introduce request-level metrics (latency, cache hit ratio, upstream call counts) and health checks for core routes. | Observability | Enable SLO dashboards and proactive alerting. | DevOps |
| Parameterize heuristic constants (BTTS weights, Elo draw factors, rolling windows) via configuration with documented defaults and review cadence. | Architecture | Easier experimentation and domain-aligned tuning. | Data Science |
| Explore dynamic weighting between market odds and Elo probabilities (e.g., performance-based blending) with experimentation guardrails. | Architecture | Improved predictive accuracy through adaptive models. | Data Science |
| Adopt automated formatting/linting (Black, Flake8) and dependency vulnerability scanning in CI. | Architecture | Consistent style and earlier detection of security drift. | Platform Engineering |
| Document deprecated endpoints and schedule their removal alongside client migration plans. | Architecture | Reduced surface area and clearer API contracts. | Product |

## Sequencing & Governance

1. **Kickoff** – Align leads on acceptance criteria, success metrics, and telemetry requirements for Priority 0 deliverables.
2. **Wave 1 Delivery** – Ship Priority 0 fixes behind feature flags if needed; validate in staging with temporary instrumentation and exercise the new CI loop on feature branches.
3. **Operationalization** – Update runbooks, on-call docs, CI configuration, and client integration guides to reflect new identifiers, logging, and caching layers.
4. **Review Cadence** – Track status weekly, attach ticket IDs to each action, and re-run all three audits (or equivalent automated checks) after Priority 1 closes to confirm remediation effectiveness; gate merges on green CI.

