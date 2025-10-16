"""Team name resolution utilities with provider-specific alias support."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache
from typing import Dict, List, Tuple

from .config import setup_logger

ALIASES_PATH = os.path.join(os.path.dirname(__file__), "data", "aliases_fbref_seed.json")

logger = setup_logger(__name__)


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


@lru_cache(maxsize=1)
def load_aliases() -> Dict[str, Dict[str, list[str]]]:
    """Load alias mappings from disk and memoize the parsed JSON."""

    with open(ALIASES_PATH, "r", encoding="utf-8") as fh:
        data: Dict[str, Dict[str, list[str]]] = json.load(fh)

    providers = set()
    for buckets in data.values():
        providers.update({provider.lower() for provider in buckets.keys()})

    ordered_providers = sorted(providers, key=lambda key: (key != "fbref", key))
    logger.info(
        "aliases: loaded %d canonicals (providers: %s)",
        len(data),
        ", ".join(ordered_providers),
    )
    return data


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
            logger.info("✅ alias '%s' → '%s' (provider=%s)", raw, canonical, provider_key)
            return canonical

    # Global aliases
    global_aliases = provider_lookup.get("_", {})
    canonical = global_aliases.get(normalized_raw)
    if canonical:
        logger.info("✅ alias '%s' → '%s' (provider=_)", raw, canonical)
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


__all__ = [
    "canonicalize_team",
    "get_all_aliases_for",
    "load_aliases",
    "resolve_team_name",
    "token_set_ratio",
]
