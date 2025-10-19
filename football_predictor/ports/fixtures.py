from typing import List, Optional, TypedDict


class TeamSide(TypedDict):
    id: int
    name: str


class Fixture(TypedDict):
    match_id: str              # provider match id as string
    competition: str           # human name (e.g., "Premier League")
    competition_code: str      # our internal code (EPL, LLIGA, ...)
    kickoff_iso: str           # ISO8601 UTC
    status: str                # "NS" | "LIVE" | "FT" | etc.
    minute: Optional[int]      # live minute when LIVE, else None
    home: TeamSide
    away: TeamSide


class FixturesPort:
    def list_competitions(self) -> List[dict]: ...

    def get_fixtures(
        self, competition_code: str, start_iso: str, end_iso: str
    ) -> List[Fixture]: ...
