import hashlib
import json
import pytest

from src.browser_engine import BrowserEngine


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None, url="https://www.marianos.com/api/v1/locations/53100503"):
        self.status = status
        self._payload = payload if payload is not None else {"data": {"store": {"locationId": "53100503"}}}
        self.headers = headers or {"content-type": "application/json"}
        self.url = url
        self._body = json.dumps(self._payload).encode("utf-8")

    def body(self):
        return self._body

    def json(self):
        return self._payload


class FakeRequestContext:
    def __init__(self, response):
        self.response = response
        self.call = None

    def get(self, url, **kwargs):
        self.call = (url, kwargs)
        return self.response


def make_engine(response):
    engine = BrowserEngine({"scraping": {"store_lookup_timeout_ms": 12000}})
    engine._context = type("Context", (), {"request": FakeRequestContext(response)})()
    return engine


def test_live_store_lookup_returns_actual_http_payload(monkeypatch):
    payload = {"data": {"store": {"locationId": "53100503"}}}
    response = FakeResponse(payload=payload)
    engine = make_engine(response)
    monkeypatch.setenv("MARIANOS_STORE_LOOKUP_URL_TEMPLATE", "https://www.marianos.com/api/v1/locations/{store_id}")

    result = engine.fetch_live_store_lookup("53100503", {"zipcode": "60601"})

    assert result["raw_store_lookup_response"] == payload
    assert result["response_metadata"]["status_code"] == 200
    assert result["response_metadata"]["provenance_type"] == "fresh_live_http_response"
    assert result["response_metadata"]["body_sha256"] == hashlib.sha256(response.body()).hexdigest()
    assert engine._context.request.call[0].endswith("/53100503")


def test_live_store_lookup_fails_closed_on_non_2xx(monkeypatch):
    engine = make_engine(FakeResponse(status=403, payload={"error": "blocked"}))
    monkeypatch.delenv("MARIANOS_STORE_LOOKUP_URL_TEMPLATE", raising=False)

    with pytest.raises(RuntimeError, match="HTTP 403"):
        engine.fetch_live_store_lookup("53100503", {"zipcode": "60601"})


def test_live_store_lookup_fails_closed_on_non_json(monkeypatch):
    class NonJsonResponse(FakeResponse):
        def json(self):
            raise ValueError("not json")

    engine = make_engine(NonJsonResponse(headers={"content-type": "text/html"}))
    with pytest.raises(RuntimeError, match="non-JSON"):
        engine.fetch_live_store_lookup("53100503", {"zipcode": "60601"})
