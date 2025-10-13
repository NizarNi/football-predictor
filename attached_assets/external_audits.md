# External Audit Inputs

## Automated Static Scan (Supplementary Audit 1)

- **Scope:** `app.py`, `config.py`, `elo_client.py`, `odds_api_client.py`, `odds_calculator.py`, `understat_client.py`, `utils.py`, `xg_data_fetcher.py`.
- **Key flags:**
  - Bare `except:` blocks in `app.py` and `xg_data_fetcher.py`.
  - Direct network usage (`requests`, `aiohttp`) and hard-coded URLs in data clients.
  - Potential secrets exposure via API key handling in `odds_api_client.py`.
  - Large modules (`xg_data_fetcher.py`) with mixed responsibilities.

## External Architecture & Quality Review (Supplementary Audit 2)

- **Highlights:**
  - Encourage precise exception handling, deduplicated endpoint logic, and consistent API responses in `app.py`.
  - Move hard-coded configuration (e.g., `next_n_days`, league mappings, rolling windows) into `config.py`.
  - Persist caches across restarts and improve logging/monitoring coverage.
  - Enhance bookmaker normalization, Elo mapping, and xG aggregation heuristics.
  - Build automated tests, adopt structured logging, and introduce formatting/linting guardrails backed by a CI loop.

