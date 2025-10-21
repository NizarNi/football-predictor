from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from ..constants import SPORTMONKS_LEAGUE_IDS, sportmonks_league_id
from ..settings import SPORTMONKS_BASE, SPORTMONKS_KEY, SPORTMONKS_TIMEOUT_MS

log = logging.getLogger(__name__)


WINNING_MARKET_KEYS = {
    "winning",
    "1x2",
    "match winner",
    "match odds",
}

STALE_ODDS_MAX_AGE = timedelta(hours=24)
DEFAULT_FIXTURE_CACHE_TTL = 300  # seconds
BOOKMAKER_CACHE_TTL = 24 * 3600  # seconds
DEFAULT_LOGO_PATH = "/static/team_logos/generic_shield.svg"


class _TTLCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: Dict[Tuple[Any, ...], Tuple[float, Any]] = {}

    def get(self, key: Tuple[Any, ...], ttl: float) -> Any:
        now = time.time()
        with self._lock:
            payload = self._store.get(key)
            if not payload:
                return None
            ts, value = payload
            if now - ts > ttl:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: Tuple[Any, ...], value: Any) -> None:
        with self._lock:
            self._store[key] = (time.time(), value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_fixture_cache = _TTLCache()
_bookmaker_cache = _TTLCache()


def _ensure_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        data = value.get("data")
        if isinstance(data, list):
            return data
        return list(value.values())
    if value is None:
        return []
    return [value]


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                if fmt.endswith("%z") and text.endswith("Z"):
                    text_mod = text[:-1] + "+00:00"
                else:
                    text_mod = text
                dt = datetime.strptime(text_mod[:len(fmt)], fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                continue
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None
    return None


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _map_status(state: Dict[str, Any]) -> Tuple[str, Optional[int]]:
    name = (state or {}).get("short_name") or (state or {}).get("name") or ""
    name = str(name).upper()
    minute: Optional[int] = None
    if name in {"NS", "NOT STARTED"}:
        return "NS", None
    if name in {"FT", "FULL-TIME", "AET"}:
        return "FT", None
    if name in {"HT", "HALF-TIME"}:
        return "HT", None
    if name in {"LIVE", "1ST HALF", "2ND HALF"}:
        return "LIVE", minute
    return name or "NS", minute


def _normalize_outcome_label(label: Any) -> Optional[str]:
    if label is None:
        return None
    text = str(label).strip().lower()
    if not text:
        return None
    if text in {"1", "home", "home team", "home win", "team1", "1 (home)"}:
        return "home"
    if text in {"x", "draw", "tie"}:
        return "draw"
    if text in {"2", "away", "away team", "away win", "team2", "2 (away)"}:
        return "away"
    return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            fval = float(value)
            if fval <= 0:
                return None
            return fval
        except Exception:
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        text = text.replace(",", ".")
        try:
            fval = float(text)
            if fval <= 0:
                return None
            return fval
        except Exception:
            return None
    return None


def _extract_market_key(entry: Dict[str, Any]) -> Optional[str]:
    def _inner(obj: Any) -> Optional[str]:
        if isinstance(obj, dict):
            if obj.get("key"):
                return str(obj.get("key")).strip().lower()
            if obj.get("name"):
                return str(obj.get("name")).strip().lower()
            data = obj.get("data")
            if isinstance(data, dict):
                return _inner(data)
        return None

    for key in ("market", "markets", "betting_market"):
        if key in entry:
            mk = _inner(entry.get(key))
            if mk:
                return mk
    if entry.get("market_name"):
        return str(entry.get("market_name")).strip().lower()
    if entry.get("market_key"):
        return str(entry.get("market_key")).strip().lower()
    return None


def _extract_outcomes(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("values", "odds", "outcomes", "results"):
        if key in entry:
            return _ensure_list(entry.get(key))
    pivot = entry.get("pivot")
    if isinstance(pivot, dict):
        for key in ("values", "odds"):
            if key in pivot:
                return _ensure_list(pivot.get(key))
    return []


def _extract_bookmaker(entry: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    bookmaker_id = entry.get("bookmaker_id") or entry.get("id")
    try:
        if bookmaker_id is not None:
            bookmaker_id = int(bookmaker_id)
    except Exception:
        bookmaker_id = None

    bookmaker_name: Optional[str] = None
    raw_bk = entry.get("bookmaker")
    if isinstance(raw_bk, dict):
        data = raw_bk.get("data") if isinstance(raw_bk.get("data"), dict) else raw_bk
        if isinstance(data, dict):
            name_candidate = data.get("name") or data.get("title")
            if name_candidate:
                bookmaker_name = str(name_candidate)
            if bookmaker_id is None and data.get("id") is not None:
                try:
                    bookmaker_id = int(data.get("id"))
                except Exception:
                    bookmaker_id = None
    if bookmaker_name:
        return bookmaker_id, bookmaker_name

    if entry.get("bookmaker_name"):
        bookmaker_name = str(entry.get("bookmaker_name"))
    return bookmaker_id, bookmaker_name


def _extract_last_update(entry: Dict[str, Any]) -> Optional[datetime]:
    for key in ("last_update", "updated_at", "last_updated", "date"):
        if key in entry:
            dt = _parse_datetime(entry.get(key))
            if dt:
                return dt
    pivot = entry.get("pivot")
    if isinstance(pivot, dict):
        for key in ("last_update", "updated_at"):
            if key in pivot:
                dt = _parse_datetime(pivot.get(key))
                if dt:
                    return dt
    return None


class SportmonksOddsAdapter:
    """Fetch Sportmonks fixtures enriched with 1X2 odds."""

    FIXTURE_INCLUDE = "participants;venue;round;odds.market:winning;odds.bookmaker"

    def __init__(
        self,
        *,
        timeout_ms: Optional[int] = None,
        fixture_cache_ttl: float = DEFAULT_FIXTURE_CACHE_TTL,
        now_fn: Optional[callable] = None,
    ) -> None:
        self.timeout = (timeout_ms or SPORTMONKS_TIMEOUT_MS) / 1000.0
        self.fixture_cache_ttl = fixture_cache_ttl
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        if SPORTMONKS_KEY:
            self._session.params.update({"api_token": SPORTMONKS_KEY})
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{SPORTMONKS_BASE}{path}"
        try:
            response = self._session.get(url, params=params, timeout=self.timeout)
        except Exception as exc:  # pragma: no cover - network errors
            log.warning("sportmonks_odds_http_error path=%s err=%s", path, exc)
            raise
        response.raise_for_status()
        try:
            return response.json() or {}
        except ValueError:
            return {}

    def _load_bookmakers(self) -> Dict[int, str]:
        try:
            data = self._request("/odds/bookmakers", params={"per_page": 200})
        except Exception:
            return {}
        rows = _ensure_list(data.get("data"))
        result: Dict[int, str] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            bid = row.get("id")
            name = row.get("name") or row.get("title")
            if bid is None or not name:
                continue
            try:
                bid_int = int(bid)
            except Exception:
                continue
            name_str = str(name)
            result[bid_int] = name_str
            _bookmaker_cache.set((bid_int,), name_str)
        return result

    def _resolve_bookmaker_name(self, bookmaker_id: Optional[int], entry: Dict[str, Any]) -> Optional[str]:
        _, name = _extract_bookmaker(entry)
        if name:
            if bookmaker_id is not None:
                _bookmaker_cache.set((bookmaker_id,), name)
            return name
        if bookmaker_id is None:
            return None
        cached = _bookmaker_cache.get((bookmaker_id,), BOOKMAKER_CACHE_TTL)
        if cached:
            return cached
        directory = self._load_bookmakers()
        return directory.get(bookmaker_id)

    def _collect_bookmaker_odds(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        market_key = _extract_market_key(entry)
        if market_key and market_key not in WINNING_MARKET_KEYS:
            return None
        outcomes_raw = _extract_outcomes(entry)
        if not outcomes_raw:
            return None
        outcomes: Dict[str, float] = {}
        for oc in outcomes_raw:
            if not isinstance(oc, dict):
                continue
            label = oc.get("label") or oc.get("name") or oc.get("outcome")
            key = _normalize_outcome_label(label)
            if not key:
                continue
            value = (
                _safe_float(oc.get("value"))
                or _safe_float(oc.get("odd"))
                or _safe_float(oc.get("decimal"))
                or _safe_float(oc.get("price"))
            )
            if value is None:
                continue
            outcomes[key] = value
        if set(outcomes.keys()) != {"home", "draw", "away"}:
            return None
        bookmaker_id, bk_name = _extract_bookmaker(entry)
        if bookmaker_id is None and bk_name:
            try:
                bookmaker_id = int(entry.get("id"))
            except Exception:
                bookmaker_id = None
        name = bk_name or self._resolve_bookmaker_name(bookmaker_id, entry)
        if bookmaker_id is None or not name:
            return None
        last_update = _extract_last_update(entry)
        if last_update:
            now = self.now_fn()
            if now - last_update > STALE_ODDS_MAX_AGE:
                return None
            last_update_iso = _to_iso(last_update)
        else:
            last_update_iso = None
        return {
            "bookmaker_id": bookmaker_id,
            "bookmaker_name": name,
            "market": "winning",
            "home": outcomes["home"],
            "draw": outcomes["draw"],
            "away": outcomes["away"],
            "last_update": last_update_iso,
        }

    def _build_odds(self, raw_odds: Any) -> Tuple[Optional[Dict[str, Any]], str]:
        entries = []
        for entry in _ensure_list(raw_odds):
            if not isinstance(entry, dict):
                continue
            bookmaker = self._collect_bookmaker_odds(entry)
            if bookmaker:
                entries.append(bookmaker)
        if not entries:
            return None, "unavailable"
        home_values = [item["home"] for item in entries if item.get("home")]
        draw_values = [item["draw"] for item in entries if item.get("draw")]
        away_values = [item["away"] for item in entries if item.get("away")]

        def _agg(values: List[float]) -> Tuple[Optional[float], Optional[float]]:
            if not values:
                return None, None
            best = max(values)
            avg = sum(values) / len(values)
            return round(best, 3), round(avg, 3)

        best_home, avg_home = _agg(home_values)
        best_draw, avg_draw = _agg(draw_values)
        best_away, avg_away = _agg(away_values)

        odds = {
            "market": "1X2",
            "source": "sportmonks",
            "best": {"home": best_home, "draw": best_draw, "away": best_away},
            "avg": {"home": avg_home, "draw": avg_draw, "away": avg_away},
            "bookmakers": entries,
        }
        return odds, "available"

    def _extract_round(self, raw: Dict[str, Any]) -> Optional[str]:
        round_obj = raw.get("round")
        if isinstance(round_obj, dict):
            if isinstance(round_obj.get("data"), dict):
                round_obj = round_obj["data"]
        if isinstance(round_obj, dict):
            name = round_obj.get("name") or round_obj.get("data")
            if isinstance(name, str):
                return name
        if isinstance(round_obj, str):
            return round_obj
        return None

    def _extract_venue(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        venue_obj = raw.get("venue")
        if isinstance(venue_obj, dict) and isinstance(venue_obj.get("data"), dict):
            venue_obj = venue_obj["data"]
        if not isinstance(venue_obj, dict):
            return {"id": None, "name": None, "city": None}
        return {
            "id": venue_obj.get("id"),
            "name": venue_obj.get("name") or venue_obj.get("stadium_name"),
            "city": venue_obj.get("city") or venue_obj.get("city_name"),
        }

    def _extract_participants(self, raw: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        participants = _ensure_list(raw.get("participants"))
        home: Dict[str, Any] = {}
        away: Dict[str, Any] = {}
        for item in participants:
            if not isinstance(item, dict):
                continue
            team = item.get("participant") or item.get("team") or item
            meta = item.get("meta") or {}
            location = str(meta.get("location", "")).lower()
            logo = team.get("image_path") or team.get("logo_path") or DEFAULT_LOGO_PATH
            if not logo:
                logo = DEFAULT_LOGO_PATH
            data = {
                "id": team.get("id"),
                "name": team.get("name"),
                "logo": logo,
            }
            if location == "home":
                home = data
            elif location == "away":
                away = data
        if not home and participants:
            team = participants[0].get("participant") if isinstance(participants[0], dict) else {}
            home = {
                "id": team.get("id"),
                "name": team.get("name"),
                "logo": team.get("image_path") or DEFAULT_LOGO_PATH,
            }
        if not away and len(participants) >= 2:
            ref = participants[1]
            team = ref.get("participant") if isinstance(ref, dict) else {}
            away = {
                "id": team.get("id"),
                "name": team.get("name"),
                "logo": team.get("image_path") or DEFAULT_LOGO_PATH,
            }
        if not home:
            home = {"id": None, "name": None, "logo": DEFAULT_LOGO_PATH}
        if not away:
            away = {"id": None, "name": None, "logo": DEFAULT_LOGO_PATH}
        return home, away

    def _build_fixture(self, raw: Dict[str, Any], competition_code: str, league_id: int) -> Optional[Dict[str, Any]]:
        fixture_id = raw.get("id")
        if fixture_id is None:
            return None
        kickoff_raw = raw.get("starting_at") or raw.get("starting_at_timestamp")
        kickoff_dt: Optional[datetime]
        if isinstance(kickoff_raw, (int, float)):
            kickoff_dt = datetime.fromtimestamp(float(kickoff_raw), tz=timezone.utc)
        else:
            kickoff_dt = _parse_datetime(kickoff_raw)
        if not kickoff_dt:
            return None
        kickoff_iso = _to_iso(kickoff_dt)
        status, minute = _map_status(raw.get("state") or {})
        home, away = self._extract_participants(raw)
        venue = self._extract_venue(raw)
        odds, odds_status = self._build_odds(raw.get("odds"))
        return {
            "match_id": str(fixture_id),
            "fixture_id": fixture_id,
            "league_id": league_id,
            "season_id": raw.get("season_id"),
            "round": self._extract_round(raw),
            "kickoff_iso": kickoff_iso,
            "datetime_utc": kickoff_iso,
            "status": status,
            "minute": minute,
            "venue": venue,
            "competition_code": competition_code,
            "home_team": home,
            "away_team": away,
            "odds": odds,
            "odds_status": odds_status,
        }

    def _fetch_fixtures_between(self, league_id: int, start: str, end: str) -> List[Dict[str, Any]]:
        cache_key = ("fixtures", league_id, start, end)
        cached = _fixture_cache.get(cache_key, self.fixture_cache_ttl)
        if cached is not None:
            return cached
        fixtures: List[Dict[str, Any]] = []
        page = 1
        while True:
            params = {
                "filters": f"league_id:{league_id}",
                "include": self.FIXTURE_INCLUDE,
                "per_page": 50,
                "page": page,
            }
            payload = self._request(f"/fixtures/between/{start}/{end}", params=params)
            rows = _ensure_list(payload.get("data"))
            fixtures.extend(row for row in rows if isinstance(row, dict))
            meta = payload.get("meta") or {}
            pagination = meta.get("pagination") if isinstance(meta, dict) else {}
            next_page = pagination.get("next_page") if isinstance(pagination, dict) else None
            if not next_page:
                break
            page = next_page
        _fixture_cache.set(cache_key, fixtures)
        return fixtures

    def get_fixtures(self, competition_code: str, start_iso: str, end_iso: str) -> List[Dict[str, Any]]:
        if not SPORTMONKS_KEY:
            log.warning("sportmonks_odds_key_missing")
            return []
        league_id = sportmonks_league_id(competition_code)
        if not league_id:
            log.info("sportmonks_odds_league_unmapped code=%s", competition_code)
            return []
        start = (start_iso or "")[:10]
        end = (end_iso or "")[:10]
        try:
            fixtures_raw = self._fetch_fixtures_between(int(league_id), start, end)
        except Exception:
            return []
        items: List[Dict[str, Any]] = []
        for raw in fixtures_raw:
            fixture = self._build_fixture(raw, competition_code, int(league_id))
            if fixture:
                items.append(fixture)
        items.sort(key=lambda it: it.get("kickoff_iso") or "")
        return items

    def list_competitions(self) -> List[Dict[str, Any]]:
        return [
            {"code": code, "league_id": lid}
            for code, lid in SPORTMONKS_LEAGUE_IDS.items()
            if lid
        ]
