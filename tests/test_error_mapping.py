import pytest

from football_predictor.errors import APIError


def test_apierror_to_dict():
    err = APIError("EloAPI", "TIMEOUT", "Elo API failed", "details")
    data = err.to_dict()
    assert data["source"] == "EloAPI"
    assert data["code"] == "TIMEOUT"
    assert "details" in data
