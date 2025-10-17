"""Request-scoped memoization helpers for rolling xG computations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Tuple

from .name_resolver import resolve_team_name
from .xg_data_fetcher import build_rolling_series, compute_rolling_xg


def _normalize_league(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value.upper() if value else None


@dataclass
class RequestMemo:
    """Holds per-request caches for match logs and rolling xG payloads."""

    team_logs: Dict[Tuple[Optional[str], Optional[int], str], Iterable[dict]] = field(
        default_factory=dict
    )
    rolling_xg: Dict[Tuple[Optional[str], Optional[int], str, int, bool], Dict[str, Any]] = (
        field(default_factory=dict)
    )
    cache_source: Dict[Tuple[Optional[str], Optional[int], str], str] = field(
        default_factory=dict
    )

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
        *,
        season: Optional[int] = None,
    ) -> None:
        """Memoize team match logs for subsequent rolling calculations."""

        league_key, canonical_team = self._canonical_key(team, league)
        if league_key is None or canonical_team is None:
            return
        key = (league_key, season, canonical_team)
        self.team_logs[key] = list(logs or [])
        if source:
            self.cache_source[key] = source

    def _resolve_existing_key(
        self, league: Optional[str], team: str, season: Optional[int]
    ) -> Tuple[Optional[str], Optional[int], str] | None:
        league_key, canonical_team = self._canonical_key(team, league)
        if canonical_team is None:
            return None

        candidates: list[Tuple[Optional[str], Optional[int], str]] = []
        for stored_league, stored_season, stored_team in self.team_logs.keys():
            if stored_team != canonical_team:
                continue
            if league_key is not None and stored_league != league_key:
                continue
            if season is None or stored_season == season:
                return stored_league, stored_season, stored_team
            candidates.append((stored_league, stored_season, stored_team))

        if candidates:
            return candidates[0]

        # Fallback across leagues if nothing matched above
        for stored_league, stored_season, stored_team in self.team_logs.keys():
            if stored_team != canonical_team:
                continue
            if season is None or stored_season == season:
                return stored_league, stored_season, stored_team
            candidates.append((stored_league, stored_season, stored_team))

        if candidates:
            return candidates[0]

        return (league_key, season, canonical_team)

    def get_or_compute_rolling(
        self,
        team: str,
        league: Optional[str],
        N: int = 5,
        *,
        season: Optional[int] = None,
        league_only: bool = True,
    ) -> Dict[str, Any]:
        """Return rolling xG arrays for a team, computing once per request."""

        resolved_key = self._resolve_existing_key(league, team, season)
        if resolved_key is None:
            return {
                "team": None,
                "league": None,
                "season": season,
                "window": int(N),
                "window_len": 0,
                "xg_for_sum": 0.0,
                "xg_against_sum": 0.0,
                "source": "all_matches" if not league_only else "league_only",
                "series": {"dates": [], "xg_for": [], "xg_against": []},
                "cache_source": None,
            }

        actual_league, actual_season, canonical_team = resolved_key
        cache_key = (
            actual_league or "",
            actual_season,
            canonical_team,
            int(N),
            bool(league_only),
        )

        if cache_key in self.rolling_xg:
            return self.rolling_xg[cache_key]

        logs = self.team_logs.get((actual_league, actual_season, canonical_team), [])
        if not logs and actual_season is None:
            # fall back to any stored season for the same league/team
            for key, stored_logs in self.team_logs.items():
                league_key, stored_season, stored_team = key
                if league_key == actual_league and stored_team == canonical_team:
                    logs = stored_logs
                    actual_season = stored_season
                    break

        xg_for_sum, xg_against_sum, window_len, source_label = compute_rolling_xg(
            list(logs or []),
            N,
            league_only=league_only,
            league=actual_league,
            team=canonical_team,
        )
        series = build_rolling_series(
            list(logs or []),
            N,
            league_only=league_only,
        ) if logs else {"dates": [], "xg_for": [], "xg_against": []}

        payload = {
            "team": canonical_team,
            "league": actual_league,
            "season": actual_season,
            "window": int(N),
            "window_len": int(window_len),
            "xg_for_sum": float(xg_for_sum),
            "xg_against_sum": float(xg_against_sum),
            "source": source_label,
            "series": series,
            "cache_source": self.cache_source.get(
                (actual_league, actual_season, canonical_team)
            ),
        }
        self.rolling_xg[cache_key] = payload
        return payload

