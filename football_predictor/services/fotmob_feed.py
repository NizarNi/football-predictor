from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple, Protocol, Iterable

from ..constants import FOTMOB_COMP_CODES
from ..composition.providers import fixtures_adapter

ISO = "%Y-%m-%dT%H:%M:%SZ"


def _parse_iso(s: Optional[str]) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        # Accept both "...Z" and "+00:00"
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(ISO)


def _clamp_window(start: datetime, end: datetime, max_days: int = 7) -> Tuple[datetime, datetime]:
    if end < start:
        start, end = end, start
    if (end - start) > timedelta(days=max_days):
        end = start + timedelta(days=max_days)
    return start, end


class FixturesAdapter(Protocol):
    def get_fixtures(self, competition_code: str, start_iso: str, end_iso: str) -> List[Dict[str, Any]]:
        ...


class FeedService:
    """
    Builds a time-ordered, multi-competition fixtures feed with cursor pagination.
    Cursor is an ISO timestamp marking the boundary of the last window sent.
    """

    DEFAULT_WINDOW_HOURS = 48  # initial +/- window around 'now'
    PAGE_SIZE_MIN = 10
    PAGE_SIZE_MAX = 50

    def __init__(self, adapter: Optional[FixturesAdapter] = None):
        self.adapter: FixturesAdapter = adapter or fixtures_adapter()

    def initial_window(self) -> Tuple[str, str]:
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=self.DEFAULT_WINDOW_HOURS)
        end = now + timedelta(hours=self.DEFAULT_WINDOW_HOURS)
        return _to_iso(start), _to_iso(end)

    def next_window(self, cursor_iso: str) -> Tuple[str, str]:
        # Move forward by DEFAULT_WINDOW_HOURS
        c = _parse_iso(cursor_iso)
        start = c
        end = c + timedelta(hours=self.DEFAULT_WINDOW_HOURS)
        return _to_iso(start), _to_iso(end)

    def prev_window(self, cursor_iso: str) -> Tuple[str, str]:
        # Move backward by DEFAULT_WINDOW_HOURS
        c = _parse_iso(cursor_iso)
        start = c - timedelta(hours=self.DEFAULT_WINDOW_HOURS)
        end = c
        return _to_iso(start), _to_iso(end)

    def _load_window(self, start_iso: str, end_iso: str, comps: List[str]) -> List[Dict[str, Any]]:
        # Fetch per-competition then merge & sort
        all_items: List[Dict[str, Any]] = []
        for code in comps:
            try:
                items = self.adapter.get_fixtures(code, start_iso, end_iso)
                all_items.extend(items or [])
            except Exception:
                # best-effort: skip failing comp
                continue
        all_items.sort(key=lambda it: it.get("kickoff_iso", ""))
        return all_items

    def load_page(
        self,
        direction: str,
        cursor: Optional[str],
        page_size_raw: Optional[str],
        comps: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        # Sanitize inputs
        direction = (direction or "future").lower()
        if direction not in ("future", "past"):
            direction = "future"

        try:
            ps = int(page_size_raw) if page_size_raw is not None else 25
        except Exception:
            ps = 25
        ps = max(self.PAGE_SIZE_MIN, min(self.PAGE_SIZE_MAX, ps))

        # Determine window
        if not cursor:
            start_iso, end_iso = self.initial_window()
        elif direction == "future":
            start_iso, end_iso = self.next_window(cursor)
        else:
            start_iso, end_iso = self.prev_window(cursor)

        # Clamp safety (<= 7 days)
        s_dt, e_dt = _parse_iso(start_iso), _parse_iso(end_iso)
        s_dt, e_dt = _clamp_window(s_dt, e_dt, max_days=7)
        start_iso, end_iso = _to_iso(s_dt), _to_iso(e_dt)

        # Load items (with small burst-forward to avoid empty screens)
        comps_list = list(comps) if comps is not None else list(FOTMOB_COMP_CODES)
        items = self._load_window(start_iso, end_iso, comps_list)
        has_more_future = True  # optimistic, we paginate by windows not count
        has_more_past = True

        # NEW: if future page is empty, walk forward up to 3 windows
        if direction == "future" and not items:
            burst = 3
            cur_start, cur_end = start_iso, end_iso
            while burst > 0 and not items:
                cur_start, cur_end = self.next_window(cur_end)
                items = self._load_window(cur_start, cur_end, comps_list)
                burst -= 1
            start_iso, end_iso = cur_start, cur_end

        # Page size is applied client-side by window; to keep it simple now, just cap to ps
        # (Later you can implement finer-grained cursoring by kickoff_iso)
        items = items[:ps] if direction == "future" else items[-ps:]

        next_cursor = end_iso if direction == "future" else cursor or end_iso
        prev_cursor = start_iso if direction == "past" else cursor or start_iso

        return {
            "items": items,
            "next_cursor": next_cursor,
            "prev_cursor": prev_cursor,
            "has_more_future": has_more_future,
            "has_more_past": has_more_past,
            "_debug": {
                "direction": direction,
                "cursor_in": cursor,
                "window": [start_iso, end_iso],
                "page_size": ps,
                "comps": comps_list,
            },
        }
