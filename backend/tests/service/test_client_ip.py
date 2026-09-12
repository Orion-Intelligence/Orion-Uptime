from __future__ import annotations

from types import SimpleNamespace

from orion.helper_manager.client_ip import client_ip


def _request(peer, forwarded=None):
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    client = SimpleNamespace(host=peer) if peer is not None else None
    return SimpleNamespace(client=client, headers=headers)


def test_returns_peer_when_no_trusted_proxies(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "")
    assert client_ip(_request("203.0.113.9", forwarded="1.1.1.1")) == "203.0.113.9"


def test_returns_unknown_when_no_client(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "")
    assert client_ip(_request(None)) == "unknown"


def test_returns_forwarded_client_when_peer_is_trusted(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.0/8")
    result = client_ip(_request("10.0.0.5", forwarded="203.0.113.7, 10.0.0.9"))
    assert result == "203.0.113.7"


def test_ignores_invalid_forwarded_entries(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.0/8")
    result = client_ip(_request("10.0.0.5", forwarded="not-an-ip, 198.51.100.4"))
    assert result == "198.51.100.4"


def test_untrusted_peer_ignores_forwarded_header(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.0/8")
    assert client_ip(_request("203.0.113.9", forwarded="1.1.1.1")) == "203.0.113.9"
