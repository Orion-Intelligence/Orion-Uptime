from starlette.requests import Request

from app.core.client_ip import client_ip


def make_request(peer: str, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    scope = {"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (peer, 1234), "query_string": b""}
    return Request(scope)


def test_peer_used_when_no_trusted_proxies(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "")
    assert client_ip(make_request("203.0.113.5", "198.51.100.7")) == "203.0.113.5"


def test_forwarded_for_used_only_from_trusted_proxy(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.0/8")
    assert client_ip(make_request("10.0.0.2", "198.51.100.7, 10.0.0.3")) == "198.51.100.7"
    assert client_ip(make_request("203.0.113.5", "198.51.100.7")) == "203.0.113.5"


def test_all_forwarded_trusted_falls_back_to_peer(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.0/8")
    assert client_ip(make_request("10.0.0.2", "10.0.0.9")) == "10.0.0.2"
