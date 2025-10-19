from typing import List, Optional, TypedDict


class Event(TypedDict):
    minute: int
    type: str                 # "goal" | "yellow" | "red" | "sub" | etc.
    team_side: str            # "home" | "away"
    team_id: int
    player: Optional[str]
    assist: Optional[str]
    detail: Optional[str]     # e.g., "penalty", "own goal"


class Events(TypedDict):
    match_id: str
    events: List[Event]       # ordered by minute


class EventsPort:
    def get_events(self, match_id: str) -> Events: ...
