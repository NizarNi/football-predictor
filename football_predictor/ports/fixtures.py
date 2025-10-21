from typing import Dict, List, Optional, TypedDict, NotRequired


class TeamSide(TypedDict):
    id: int
    name: str
    display_name: NotRequired[str]
    slug: NotRequired[Optional[str]]
    score: NotRequired[Optional[int]]
    logo: NotRequired[Optional[str]]


class Fixture(TypedDict):
    match_id: str              # provider match id as string
    competition: str           # human name (e.g., "Premier League")
    competition_code: str      # our internal code (EPL, LLIGA, ...)
    kickoff_iso: str           # ISO8601 UTC
    status: str                # "NS" | "LIVE" | "FT" | etc.
    minute: Optional[int]      # live minute when LIVE, else None
    home: TeamSide
    away: TeamSide
    fixture_id: NotRequired[int]
    league_id: NotRequired[int]
    season_id: NotRequired[int]
    round: NotRequired[Optional[str]]
    venue: NotRequired[Dict[str, Optional[str]]]
    kickoff_utc: NotRequired[str]
    tv_stations: NotRequired[List[str]]
    referee: NotRequired[Optional[str]]


class FixturesPort:
    def list_competitions(self) -> List[dict]: ...

    def get_fixtures(
        self, competition_code: str, start_iso: str, end_iso: str
    ) -> List[Fixture]: ...
