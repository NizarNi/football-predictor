from typing import List, TypedDict


class StandingRow(TypedDict):
    team_id: int
    team: str
    played: int
    wins: int
    draws: int
    losses: int
    pts: int
    gd: int


class Standings(TypedDict):
    competition_code: str
    season: str
    table: List[StandingRow]


class StandingsPort:
    def get_standings(self, competition_code: str, season: str) -> Standings: ...
