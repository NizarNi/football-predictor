from flask import jsonify
from typing import Any, Optional


def make_ok(data: Optional[Any] = None, message: str = "success", status_code: int = 200):
    """Return a standardized success response."""
    response = {
        "status": "ok",
        "message": message,
        "data": data,
    }
    return jsonify(response), status_code


def make_error(error: Any, message: str = "An error occurred", status_code: int = 400):
    """Return a standardized error response."""
    response = {
        "status": "error",
        "message": message,
        "error": error,
    }
    return jsonify(response), status_code
