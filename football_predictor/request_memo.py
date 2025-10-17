"""Request-scoped memoization helpers for rolling xG computations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Tuple

from .name_resolver import resolve_team_name
from .xg_data_fetcher import compute_rolling_xg


def _normalize_league(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value.upper() if value else None


@dataclass
class RequestMemo:
    """Holds per-request caches for match logs and rolling xG payloads."""

    team_logs: Dict[Tuple[str, str], Iterable[dict]] = field(default_factory=dict)
    rolling_xg: Dict[Tuple[str, str, int], Dict[str, Any]] = field(default_factory=dict)
    cache_source: Dict[Tuple[str, str], str] = field(default_factory=dict)

    def _canonical_key(self, team: str, league: Optional[str]) -> Tuple[Optional[str], str]:
        canonical_team = resolve_team_name(team, provider="fbref") if team else team
        league_key = _normalize_league(league)
        return league_key, canonical_team

    def remember_team_logs(
        self,
        league: str,
        team: str,
        logs: Iterable[dict],
        source: Optional[str] = None,
    ) -> None:
        """Memoize team match logs for subsequent rolling calculations."""

        league_key, canonical_team = self._canonical_key(team, league)
        if league_key is None or canonical_team is None:
            return
        self.team_logs[(league_key, canonical_team)] = list(logs or [])
        if source:
            self.cache_source[(league_key, canonical_team)] = source

    def _resolve_existing_key(
        self, league: Optional[str], team: str
    ) -> Tuple[Optional[str], str] | None:
        league_key, canonical_team = self._canonical_key(team, league)
        if canonical_team is None:
            return None

        if league_key is not None and (league_key, canonical_team) in self.team_logs:
            return league_key, canonical_team

        # Fallback: locate any stored league for the canonical team
        for stored_league, stored_team in self.team_logs.keys():
            if stored_team == canonical_team:
                return stored_league, stored_team

        return (league_key, canonical_team)

    def get_or_compute_rolling(
        self,
        team: str,
        league: Optional[str],
        N: int = 5,
    ) -> Dict[str, Any]:
        """Return rolling xG arrays for a team, computing once per request."""

        resolved_key = self._resolve_existing_key(league, team)
        if resolved_key is None:
            return {
                "for": [],
                "against": [],
                "dates": [],
                "window_len": 0,
                "source_label": "league_only",
                "cache_source": None,
            }

        actual_league, canonical_team = resolved_key
        cache_key = (actual_league or "", canonical_team, N)

        if cache_key in self.rolling_xg:
            return self.rolling_xg[cache_key]

        logs = self.team_logs.get((actual_league, canonical_team), [])
        rolling_payload = compute_rolling_xg(
            logs,
            N,
            league_only=True,
            league=actual_league,
            team=canonical_team,
        )

        rolling_payload["cache_source"] = self.cache_source.get(
            (actual_league, canonical_team)
        )
        self.rolling_xg[cache_key] = rolling_payload
        return rolling_payload

