from flask import jsonify


def make_error(message, code):
    """Return a standardized error response."""
    return jsonify({"success": False, "error": message}), code


def make_ok(payload):
    """Return a standardized success response."""
    return jsonify({"success": True, "data": payload})
