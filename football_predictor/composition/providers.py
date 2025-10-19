import os
from dataclasses import dataclass
from typing import Optional

# Import your real adapters here when available
# from football_predictor.infra.xg.fbref_understat_adapter import FbrefXgAdapter
# from football_predictor.infra.xg.fotmob_adapter import FotmobXgAdapter
# from football_predictor.infra.standings.uefa_adapter import UefaStandingsAdapter
# from football_predictor.infra.standings.football_data_adapter import FootballDataStandingsAdapter
# from football_predictor.infra.standings.fotmob_adapter import FotmobStandingsAdapter
# from football_predictor.infra.live.scoreboard_adapter import ScoreboardLiveAdapter
# from football_predictor.infra.live.fotmob_adapter import FotmobLiveAdapter


@dataclass
class Providers:
    standings: Optional[object] = None
    standings_shadow: Optional[object] = None
    xg: Optional[object] = None
    xg_shadow: Optional[object] = None
    live: Optional[object] = None


def build_providers() -> Providers:
    sp = os.getenv("STANDINGS_PROVIDER", "uefa")
    sp_shadow = os.getenv("STANDINGS_SHADOW_PROVIDER", "none")
    xg = os.getenv("XG_PROVIDER", "fbref")
    xg_shadow = os.getenv("XG_SHADOW_PROVIDER", "none")
    live = os.getenv("LIVE_PROVIDER", "none")

    prov = Providers()

    # Standings (plug real adapters when present)
    if sp == "fotmob":
        prov.standings = None  # FotmobStandingsAdapter()
    elif sp == "uefa":
        prov.standings = None  # UefaStandingsAdapter()
    elif sp == "football_data":
        prov.standings = None  # FootballDataStandingsAdapter()

    if sp_shadow == "fotmob":
        prov.standings_shadow = None  # FotmobStandingsAdapter()
    elif sp_shadow == "football_data":
        prov.standings_shadow = None  # FootballDataStandingsAdapter()
    elif sp_shadow == "uefa":
        prov.standings_shadow = None  # UefaStandingsAdapter()

    # XG
    if xg == "fbref":
        prov.xg = None  # FbrefXgAdapter()
    elif xg == "fotmob":
        prov.xg = None  # FotmobXgAdapter()

    if xg_shadow == "fotmob":
        prov.xg_shadow = None  # FotmobXgAdapter()
    elif xg_shadow == "fbref":
        prov.xg_shadow = None  # FbrefXgAdapter()

    # Live
    if live == "fotmob":
        prov.live = None  # FotmobLiveAdapter()
    elif live == "scoreboard":
        prov.live = None  # ScoreboardLiveAdapter()

    return prov
