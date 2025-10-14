from flask import jsonify, request
from typing import Any, Dict, Optional


# Routes that must continue returning legacy (unwrapped) JSON so the
# front-end can consume the responses without modifications.
_LEGACY_EXACT_PATHS = {
    "/upcoming",
    "/search",
    "/career_xg",
}

# All nested `/match/...` endpoints previously returned unwrapped payloads.
_LEGACY_PREFIXES = ("/match/",)


def _is_legacy_request() -> bool:
    """Determine if the current request should return legacy JSON."""

    try:
        path = request.path  # type: ignore[attr-defined]
    except RuntimeError:
        # Outside of a request context (e.g., during CLI usage or tests),
        # default to wrapped responses.
        return False

    if not path:
        return False

    if path in _LEGACY_EXACT_PATHS:
        return True

    return any(path.startswith(prefix) for prefix in _LEGACY_PREFIXES)


def _build_success_payload(data: Optional[Any], message: str) -> Dict[str, Any] | Any:
    if _is_legacy_request():
        # Legacy endpoints historically returned the raw data structure.
        return data if data is not None else {}

    return {
        "status": "ok",
        "message": message,
        "data": data,
    }


def _build_error_payload(error: Any, message: str) -> Dict[str, Any] | Any:
    if _is_legacy_request():
        legacy_payload = {"error": error}
        if message:
            legacy_payload["message"] = message
        return legacy_payload

    return {
        "status": "error",
        "message": message,
        "error": error,
    }


def make_ok(data: Optional[Any] = None, message: str = "success", status_code: int = 200):
    """Return a standardized success response."""

    payload = _build_success_payload(data, message)
    response = jsonify(payload)
    return response, status_code


def make_error(error: Any, message: str = "An error occurred", status_code: int = 400):
    """Return a standardized error response."""

    payload = _build_error_payload(error, message)
    response = jsonify(payload)
    return response, status_code
