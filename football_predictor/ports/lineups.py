from typing import List, Optional, TypedDict


class PlayerEntry(TypedDict):
    number: Optional[int]
    name: str
    pos: Optional[str]
    on: int                   # minute on (0 for starter)
    off: Optional[int]        # minute off (None if on at FT)


class TeamLineup(TypedDict):
    team_id: int
    team_name: str
    formation: Optional[str]
    starters: List[PlayerEntry]
    bench: List[PlayerEntry]


class Lineups(TypedDict):
    match_id: str
    home: TeamLineup
    away: TeamLineup


class LineupsPort:
    def get_lineups(self, match_id: str) -> Lineups: ...
