# Code Audit Report

## Overview
This audit highlights key reliability risks spotted during a quick review of the current code base. The focus was on production-impacting issues around match identifiers, odds aggregation, and API key management.

## Findings

### 1. Non-deterministic match identifiers
Upcoming match payloads replace the Odds API `event_id` with Python's built-in `hash()` value. Because hash randomization changes between interpreter processes, the generated IDs are unstable across deployments and even across server restarts. That breaks permalink expectations for clients (e.g., caching, bookmarking, or follow-up requests by ID) and risks collisions when the hash output overlaps.【F:football_predictor/odds_api_client.py†L146-L159】

**Suggestion:** Return the provider's original `event_id`, or generate a stable UUID derived from it (e.g., SHA-256) instead of relying on `hash()`.

### 2. Fragile team name matching when aggregating odds
Odds aggregation only accepts outcomes whose `name` exactly matches the home or away team strings coming from the schedule feed, while draws are matched case-insensitively. Bookmakers frequently abbreviate or localize team names ("Man Utd" vs. "Manchester United"), so these comparisons quietly discard many prices. The algorithm then falls back to the default 0.33 probability for the missing side, skewing win probabilities, confidence, and arbitrage detection.【F:football_predictor/odds_calculator.py†L12-L47】

**Suggestion:** Normalize bookmaker outcome names (casefold, strip accents, apply the same `normalize_team_name` helper, and/or leverage the existing `fuzzy_team_match`) before comparison so that equivalent names merge correctly.

### 3. API key rotation is not thread-safe
The Odds API client rotates keys via shared module-level state (`current_key_index` and `invalid_keys`) that is mutated without synchronization. Under a multi-threaded WSGI server, concurrent requests can interleave updates to these globals, producing inconsistent indices, skipping keys, or even raising `IndexError`.【F:football_predictor/odds_api_client.py†L17-L80】

**Suggestion:** Protect key rotation with a threading lock (or move the state into a process-local worker) so that only one request mutates the rotation state at a time.

## Next Steps
Addressing the issues above will make downstream APIs more predictable, reduce bad probability calculations, and harden production stability when scaling the Flask app. A consolidated remediation backlog that combines these items with findings from external security and observability reviews lives in `ACTION_PLAN.md`.
