import sys
import types

import pytest


if "aiohttp" not in sys.modules:
    aiohttp_stub = types.ModuleType("aiohttp")
    aiohttp_stub.ClientSession = object
    aiohttp_stub.ClientError = Exception
    aiohttp_stub.ClientTimeout = lambda *args, **kwargs: None
    sys.modules["aiohttp"] = aiohttp_stub

if "understat" not in sys.modules:
    understat_stub = types.ModuleType("understat")

    class _UnderstatStub:  # pragma: no cover - stub for import-time dependency
        def __init__(self, *args, **kwargs):
            pass

    understat_stub.Understat = _UnderstatStub
    sys.modules["understat"] = understat_stub

from football_predictor import understat_client


def test_retry_backoff(monkeypatch):
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(args)
        raise understat_client.requests.RequestException("boom")

    monkeypatch.setattr(understat_client.requests, "get", fake_get)
    monkeypatch.setattr(understat_client.time, "sleep", lambda *_: None)

    with pytest.raises(RuntimeError):
        understat_client.fetch_with_backoff("http://fake")

    assert len(calls) == understat_client.MAX_RETRIES


def test_success_after_retry(monkeypatch):
    attempts = [1, 2, 3]

    def fake_get(*args, **kwargs):
        attempt = attempts.pop(0)
        if attempt < 3:
            raise understat_client.requests.RequestException("fail")

        class Resp:
            status_code = 200
            text = "{}"

        return Resp()

    monkeypatch.setattr(understat_client.requests, "get", fake_get)
    monkeypatch.setattr(understat_client.time, "sleep", lambda *_: None)

    response = understat_client.fetch_with_backoff("http://ok")

    assert response.status_code == 200
