"""Developer-only Sportmonks probe utilities.

This script performs lightweight smoke tests against the Sportmonks
Football API. Provide one or more league identifiers to verify their
visibility. Afterwards a fixtures between call is executed to ensure the
endpoint is responsive.

Usage::

    python -m scripts.smonks_probe 8 564 384
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from typing import Iterable

import requests

try:  # Prefer loading dotenv if it is available in the environment.
    from dotenv import load_dotenv, find_dotenv
except Exception:  # pragma: no cover - optional dependency.
    load_dotenv = find_dotenv = None  # type: ignore[assignment]


DEFAULT_BASE_URL = "https://api.sportmonks.com/v3/football"
TIMEOUT = 20


def _load_env() -> None:
    if load_dotenv is None or find_dotenv is None:
        return
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path)


def _sportmonks_key() -> str | None:
    key = os.getenv("SPORTMONKS_KEY")
    if key:
        return key
    key_file = os.getenv("SPORTMONKS_KEY_FILE")
    if key_file and os.path.exists(key_file):
        with open(key_file, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    return None


def _sportmonks_base() -> str:
    return os.getenv("SPORTMONKS_BASE", DEFAULT_BASE_URL).rstrip("/")


def probe_leagues(league_ids: Iterable[str], *, base: str, key: str) -> None:
    for league_id in league_ids:
        url = f"{base}/leagues/{league_id}"
        try:
            response = requests.get(url, params={"api_token": key}, timeout=TIMEOUT)
        except requests.RequestException as exc:  # pragma: no cover - network failure.
            print(f"league {league_id} request failed ✗ ({exc})")
            continue
        if response.status_code == 200:
            print(f"league {league_id} visible ✓")
        else:
            print(f"league {league_id} invisible ✗ ({response.status_code})")


def probe_fixtures(*, base: str, key: str) -> None:
    today = _dt.date.today()
    start = (today - _dt.timedelta(days=7)).isoformat()
    end = (today + _dt.timedelta(days=7)).isoformat()
    url = f"{base}/fixtures/between/{start}/{end}"
    try:
        response = requests.get(url, params={"api_token": key}, timeout=TIMEOUT)
    except requests.RequestException as exc:  # pragma: no cover - network failure.
        print(f"fixtures between request failed ✗ ({exc})")
        return
    if response.status_code == 200:
        payload = response.json()
        fixtures = payload.get("data") if isinstance(payload, dict) else None
        count = len(fixtures) if isinstance(fixtures, list) else "unknown"
        print(f"fixtures between count: {count}")
    else:
        print(f"fixtures between invisible ✗ ({response.status_code})")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    _load_env()
    base = _sportmonks_base()
    key = _sportmonks_key()
    if not key:
        print("SPORTMONKS_KEY or SPORTMONKS_KEY_FILE must be set.", file=sys.stderr)
        return 1
    if not argv:
        print("Usage: python -m scripts.smonks_probe <league_id> [<league_id> ...]", file=sys.stderr)
        return 2

    probe_leagues(argv, base=base, key=key)
    probe_fixtures(base=base, key=key)
    return 0


if __name__ == "__main__":  # pragma: no cover - manual execution.
    sys.exit(main())
