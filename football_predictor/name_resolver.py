"""Team name resolution utilities with provider-specific alias support."""
from __future__ import annotations

import json
import logging
import os
import re
import time
import unicodedata
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from threading import Event, Lock
from typing import Dict, List, Optional, Set, Tuple

from .config import setup_logger
from .logging_utils import RateLimitedLogger, warn_once, reset_warn_once_cache

ALIASES_PATH = os.path.join(os.path.dirname(__file__), "data", "aliases_fbref_seed.json")

logger = setup_logger(__name__)

LOG_THROTTLE_INTERVAL = float(os.environ.get("LOG_THROTTLE_INTERVAL", "300"))
_alias_debug_throttle = RateLimitedLogger(logger, window_seconds=LOG_THROTTLE_INTERVAL)
_alias_suppressed_lock = Lock()
_alias_suppressed_count = 0
_alias_suppressed_sample: Optional[Tuple[str, str, str]] = None
_alias_suppressed_last_emit = time.monotonic()

_alias_dedupe: ContextVar[Optional[Set[Tuple[str, str, str]]]] = ContextVar(
    "alias_dedupe", default=None
)
_alias_providers: ContextVar[Optional[Set[str]]] = ContextVar(
    "alias_providers", default=None
)
_alias_seed_used: ContextVar[bool] = ContextVar("alias_seed_used", default=False)

_resolver_ready_logged = False

RESOLVER_READY_EVENT: Event = Event()
_resolver_lock: Lock = Lock()
RESOLVER_READY: bool = False
_resolver_providers: List[str] = []
_seed_alias_cache: Optional[Dict[str, Dict[str, list[str]]]] = None
_seed_providers: Optional[List[str]] = None
_hydrated_alias_cache: Optional[Dict[str, Dict[str, list[str]]]] = None
_seed_fallback_count: int = 0


def _compute_provider_order(aliases: Dict[str, Dict[str, list[str]]]) -> List[str]:
    providers: Set[str] = set()
    for buckets in aliases.values():
        providers.update(provider.lower() for provider in buckets.keys())
    ordered = sorted(providers, key=lambda key: (key != "fbref", key))
    return ordered


def _load_seed_aliases() -> Dict[str, Dict[str, list[str]]]:
    global _seed_alias_cache, _seed_providers
    if _seed_alias_cache is None:
        with open(ALIASES_PATH, "r", encoding="utf-8") as fh:
            _seed_alias_cache = json.load(fh)
        _seed_providers = _compute_provider_order(_seed_alias_cache)
    return _seed_alias_cache


def _load_hydrated_aliases() -> Dict[str, Dict[str, list[str]]]:
    global _hydrated_alias_cache
    if _hydrated_alias_cache is None:
        # Phase 5 stabilization: hydration mirrors the static seed payload.
        _hydrated_alias_cache = _load_seed_aliases()
    return _hydrated_alias_cache


def _mark_seed_used() -> None:
    global _seed_fallback_count
    if not _alias_seed_used.get():
        _alias_seed_used.set(True)
        _seed_fallback_count += 1
    warn_once(
        "alias_resolver_seed",
        "Alias resolver still warming – using static alias seed for this request.",
        logger=logger,
    )


def _flush_alias_suppressed(force: bool = False) -> None:
    global _alias_suppressed_count, _alias_suppressed_sample, _alias_suppressed_last_emit

    with _alias_suppressed_lock:
        if _alias_suppressed_count <= 0:
            return
        now = time.monotonic()
        if not force and (now - _alias_suppressed_last_emit) < LOG_THROTTLE_INTERVAL:
            return
        sample = _alias_suppressed_sample
        count = _alias_suppressed_count
        _alias_suppressed_count = 0
        _alias_suppressed_sample = None
        _alias_suppressed_last_emit = now

    if not sample:
        return

    raw, canonical, _provider = sample
    logger.info(
        "alias_normalizer: suppressed %d duplicate mappings (e.g. '%s'→'%s')",
        count,
        raw,
        canonical,
    )


def _record_alias_suppression(raw: str, canonical: str, provider: str) -> None:
    global _alias_suppressed_count, _alias_suppressed_sample

    with _alias_suppressed_lock:
        _alias_suppressed_count += 1
        if _alias_suppressed_sample is None:
            _alias_suppressed_sample = (raw, canonical, provider)

    _flush_alias_suppressed()


def _register_alias_mapping(raw: str, canonical: str, provider: str) -> None:
    mapping = (raw, canonical, provider)
    bucket = _alias_dedupe.get()
    if bucket is not None:
        bucket.add(mapping)
    provider_bucket = _alias_providers.get()
    if provider_bucket is not None:
        provider_bucket.add(provider)
    if _alias_debug_throttle.log(
        logging.DEBUG, (raw, canonical, provider), "✅ alias '%s' → '%s' (provider=%s)", raw, canonical, provider
    ):
        _flush_alias_suppressed()
    else:
        _record_alias_suppression(raw, canonical, provider)


@contextmanager
def alias_logging_context() -> None:
    """Context manager to aggregate alias normalization summaries."""

    token_bucket = _alias_dedupe.set(set())
    token_providers = _alias_providers.set(set())
    token_seed = _alias_seed_used.set(False)
    try:
        yield
    finally:
        mappings = _alias_dedupe.get()
        providers = _alias_providers.get()
        provider_list = sorted(providers) if providers else []
        providers_display = ", ".join(provider_list) if provider_list else "none"
        if _alias_seed_used.get():
            providers_display = (
                f"{providers_display} (seed)" if providers_display else "seed"
            )
        logger.info(
            "alias_normalizer: applied %d unique mappings (providers: %s)",
            len(mappings) if mappings is not None else 0,
            providers_display,
        )
        _flush_alias_suppressed()
        _alias_dedupe.reset(token_bucket)
        _alias_providers.reset(token_providers)
        _alias_seed_used.reset(token_seed)


def _norm(value: str) -> str:
    """Return a normalized identifier string for fuzzy/alias matching."""

    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^\w&' ]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def canonicalize_team(raw: str | None) -> str:
    """Canonicalize a raw team string for alias lookups."""

    if raw is None:
        return ""
    return _norm(str(raw))


def token_set_ratio(a: str, b: str) -> int:
    """Compute a token set similarity ratio between two strings (0-100)."""

    sa, sb = set(canonicalize_team(a).split()), set(canonicalize_team(b).split())
    if not sa or not sb:
        return 0
    inter = len(sa & sb)
    union = len(sa | sb)
    if union == 0:
        return 0
    return int(100 * inter / union)


def load_aliases() -> Dict[str, Dict[str, list[str]]]:
    """Load alias mappings from disk and memoize the parsed JSON."""
    global RESOLVER_READY

    if RESOLVER_READY or RESOLVER_READY_EVENT.is_set():
        RESOLVER_READY = True
        return _load_hydrated_aliases()

    if RESOLVER_READY_EVENT.wait(0):
        RESOLVER_READY = True
        return _load_hydrated_aliases()

    _mark_seed_used()
    return _load_seed_aliases()


def resolver_seed_used() -> bool:
    """Return whether the current context fell back to the static alias seed."""

    return bool(_alias_seed_used.get())


def await_resolver_ready(timeout: Optional[float] = None) -> bool:
    """Block until the resolver hydration completes (returns True if ready)."""

    ready = RESOLVER_READY_EVENT.wait(timeout)
    if ready:
        global RESOLVER_READY
        RESOLVER_READY = True
    return ready


def resolver_providers() -> List[str]:
    if RESOLVER_READY or RESOLVER_READY_EVENT.is_set():
        return list(_resolver_providers)
    return list(_seed_providers or _compute_provider_order(_load_seed_aliases()))


def _hydrate_aliases() -> List[str]:
    aliases = _load_hydrated_aliases()
    ordered = _compute_provider_order(aliases)
    logger.info(
        "aliases: loaded %d canonicals (providers: %s)",
        len(aliases),
        ", ".join(ordered) if ordered else "none",
    )
    return ordered


def get_all_aliases_for(canonical: str) -> list[str]:
    """Return every known alias for a canonical club name."""

    aliases = load_aliases()
    buckets = aliases.get(canonical, {})
    combined: List[str] = []
    for key in ("_", "fbref"):
        for alias in buckets.get(key, []):
            if alias not in combined:
                combined.append(alias)
    return combined


@lru_cache(maxsize=1)
def _build_lookup_structures() -> Tuple[Dict[str, str], Dict[str, Dict[str, str]]]:
    """Construct reverse lookup dictionaries for alias resolution."""

    aliases = load_aliases()
    canonical_by_norm: Dict[str, str] = {}
    provider_lookup: Dict[str, Dict[str, str]] = {}

    for canonical, buckets in aliases.items():
        canonical_key = canonicalize_team(canonical)
        canonical_by_norm[canonical_key] = canonical
        for provider, names in buckets.items():
            normalized_provider = provider.lower()
            lookup = provider_lookup.setdefault(normalized_provider, {})
            for alias in names:
                lookup[canonicalize_team(alias)] = canonical

    return canonical_by_norm, provider_lookup


def warm_alias_resolver(*, blocking: bool = True) -> List[str]:
    """Preload alias providers at startup and log readiness once."""

    global _resolver_ready_logged, _resolver_providers, RESOLVER_READY

    if RESOLVER_READY_EVENT.is_set() and _resolver_providers:
        return list(_resolver_providers)

    if not blocking:
        from threading import Thread

        def _async_warm() -> None:
            try:
                warm_alias_resolver(blocking=True)
            except Exception:  # pragma: no cover - best-effort log
                logger.exception("Alias resolver warm-up failed")

        Thread(target=_async_warm, daemon=True).start()
        return resolver_providers()

    with _resolver_lock:
        if RESOLVER_READY_EVENT.is_set() and _resolver_providers:
            return list(_resolver_providers)

        ordered = _hydrate_aliases()
        _resolver_providers = list(ordered)
        RESOLVER_READY = True
        RESOLVER_READY_EVENT.set()
        _build_lookup_structures.cache_clear()
        _build_lookup_structures()
        if not _resolver_ready_logged:
            providers_display = ", ".join(ordered) if ordered else "none"
            logger.info("Resolver ready: providers=%s", providers_display)
            _resolver_ready_logged = True
        return list(_resolver_providers)


def resolve_team_name(raw: str, provider: str | None = None) -> str:
    """Resolve a raw team name into a canonical club name.

    Args:
        raw: The raw team name from any upstream source.
        provider: Optional provider identifier to scope alias lookups.

    Returns:
        Canonical team name if resolved; otherwise returns the original input.
    """

    if raw is None:
        return raw

    provider_key = provider.lower() if provider else None
    aliases = load_aliases()
    canonical_by_norm, provider_lookup = _build_lookup_structures()
    normalized_raw = canonicalize_team(raw)

    # Direct canonical match
    canonical = canonical_by_norm.get(normalized_raw)
    if canonical:
        return canonical

    # Provider-specific aliases
    if provider_key:
        provider_aliases = provider_lookup.get(provider_key, {})
        canonical = provider_aliases.get(normalized_raw)
        if canonical:
            _register_alias_mapping(raw, canonical, provider_key)
            return canonical

    # Global aliases
    global_aliases = provider_lookup.get("_", {})
    canonical = global_aliases.get(normalized_raw)
    if canonical:
        _register_alias_mapping(raw, canonical, "_")
        return canonical

    # Fuzzy match against canonical names and provider aliases
    best_match = None
    best_score = 0

    for canonical_name, buckets in aliases.items():
        score = token_set_ratio(raw, canonical_name)
        if score > best_score:
            best_match = canonical_name
            best_score = score
        if provider_key:
            for alias in buckets.get(provider_key, []):
                score = token_set_ratio(raw, alias)
                if score > best_score:
                    best_match = canonical_name
                    best_score = score
        for alias in buckets.get("_", []):
            score = token_set_ratio(raw, alias)
            if score > best_score:
                best_match = canonical_name
                best_score = score

    if best_match and best_score >= 85:
        logger.debug("~ fuzzy '%s' → '%s' (score=%d)", raw, best_match, best_score)
        return best_match

    return raw


def get_seed_fallback_count() -> int:
    """Return how many times the seed fallback has been used."""

    return _seed_fallback_count


def _reset_resolver_state_for_tests() -> None:  # pragma: no cover - testing helper
    global RESOLVER_READY, _resolver_providers, _hydrated_alias_cache, _seed_fallback_count
    RESOLVER_READY = False
    RESOLVER_READY_EVENT.clear()
    _resolver_providers = []
    _hydrated_alias_cache = None
    _seed_fallback_count = 0
    _build_lookup_structures.cache_clear()
    reset_warn_once_cache()


def _reset_alias_log_throttle_for_tests(interval: Optional[float] = None) -> None:
    global LOG_THROTTLE_INTERVAL, _alias_debug_throttle, _alias_suppressed_last_emit

    target = LOG_THROTTLE_INTERVAL if interval is None else float(interval)
    LOG_THROTTLE_INTERVAL = target
    _alias_debug_throttle = RateLimitedLogger(logger, window_seconds=target)
    with _alias_suppressed_lock:
        global _alias_suppressed_count, _alias_suppressed_sample
        _alias_suppressed_count = 0
        _alias_suppressed_sample = None
        _alias_suppressed_last_emit = time.monotonic()


__all__ = [
    "canonicalize_team",
    "alias_logging_context",
    "await_resolver_ready",
    "get_all_aliases_for",
    "get_seed_fallback_count",
    "load_aliases",
    "resolver_providers",
    "resolver_seed_used",
    "resolve_team_name",
    "token_set_ratio",
    "warm_alias_resolver",
    "_reset_alias_log_throttle_for_tests",
]
