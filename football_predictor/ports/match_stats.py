from typing import List, Optional, TypedDict


class TeamXG(TypedDict):
    team_id: int
    team_name: str
    xg: float


class Shot(TypedDict):
    team_id: int
    team_side: str            # "home" | "away"
    minute: int
    x: float                  # normalized [0..1] pitch coords if available
    y: float
    xg: float
    outcome: str              # "Goal" | "Saved" | etc.
    player: Optional[str]


class MatchStats(TypedDict):
    match_id: str
    competition: str
    kickoff_iso: str
    status: str
    teams: List[TeamXG]       # two entries (home/away) with totals
    shots: List[Shot]         # may be empty when unavailable


class MatchStatsPort:
    def get_match_stats(self, match_id: str) -> MatchStats: ...
