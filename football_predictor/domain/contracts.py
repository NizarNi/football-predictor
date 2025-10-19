from typing import Any, Dict, List, Optional, TypedDict


class TeamXgSnapshot(TypedDict, total=False):
    xg_for_per_game: float
    xg_against_per_game: float
    # Optional FotMob enrichments
    xgot_for_per_game: Optional[float]
    xgot_against_per_game: Optional[float]
    big_chances_for: Optional[float]
    big_chances_against: Optional[float]
    shots_on_target_per_game: Optional[float]
    shots_total_per_game: Optional[float]
    possession_pct: Optional[float]
    accurate_pass_pct: Optional[float]
    shots: Optional[List[Dict[str, Any]]]


class StandingsTable(TypedDict):
    rows: List[Dict[str, Any]]
    source: str


class LiveEvent(TypedDict):
    id: str
    home: str
    away: str
    score: str
    clock: str
    status: str


class IStandingsProvider:
    def list_competition_standings(
        self, competition: str, season: Optional[int] = None
    ) -> StandingsTable:
        ...


class IXgProvider:
    def league_snapshot(self, league: str) -> Dict[str, TeamXgSnapshot]:
        ...

    def team_rolling_xg(self, league: str, team: str) -> TeamXgSnapshot:
        ...


class IMatchOddsProvider:
    def list_upcoming(self, competition: Optional[str] = None) -> List[Dict[str, Any]]:
        ...

    def get_event_odds(self, event_id: str, market: str) -> Dict[str, Any]:
        ...


class ILiveScoreProvider:
    def live_events(self, competition: Optional[str] = None) -> List[LiveEvent]:
        ...
