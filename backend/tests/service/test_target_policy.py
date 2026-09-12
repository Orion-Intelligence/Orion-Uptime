from __future__ import annotations

import asyncio
import socket

import pytest

from orion.helper_manager import target_policy
from orion.shared_models.exceptions import ValidationError


def _addrinfo(*addresses):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 0)) for address in addresses]



def test_is_public_address():
    assert target_policy._is_public_address("8.8.8.8") is True
    assert target_policy._is_public_address("127.0.0.1") is False
    assert target_policy._is_public_address("10.0.0.1") is False


def test_private_targets_allowed_reads_env(monkeypatch):
    monkeypatch.setenv("MONITOR_ALLOW_PRIVATE_TARGETS", "true")
    assert target_policy.private_targets_allowed() is True
    monkeypatch.setenv("MONITOR_ALLOW_PRIVATE_TARGETS", "false")
    assert target_policy.private_targets_allowed() is False


def test_validate_target_url_rejects_bad_scheme_host_and_credentials(monkeypatch):
    monkeypatch.setenv("MONITOR_ALLOW_PRIVATE_TARGETS", "true")
    with pytest.raises(ValidationError):
        asyncio.run(target_policy.validate_target_url("ftp://example.com"))
    with pytest.raises(ValidationError):
        asyncio.run(target_policy.validate_target_url("https://"))
    with pytest.raises(ValidationError):
        asyncio.run(target_policy.validate_target_url("https://user:pass@example.com"))


def test_validate_target_url_allows_valid_public_url(monkeypatch):
    monkeypatch.setenv("MONITOR_ALLOW_PRIVATE_TARGETS", "false")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: _addrinfo("93.184.216.34"))
    asyncio.run(target_policy.validate_target_url("https://example.com/status"))


def test_validate_target_host_blocks_private_resolution(monkeypatch):
    monkeypatch.setenv("MONITOR_ALLOW_PRIVATE_TARGETS", "false")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: _addrinfo("10.0.0.5"))
    with pytest.raises(ValidationError):
        asyncio.run(target_policy.validate_target_host("internal.example.com"))


def test_validate_target_host_allows_private_when_configured(monkeypatch):
    monkeypatch.setenv("MONITOR_ALLOW_PRIVATE_TARGETS", "true")
    asyncio.run(target_policy.validate_target_host("localhost"))


def test_validate_target_host_requires_a_host(monkeypatch):
    monkeypatch.setenv("MONITOR_ALLOW_PRIVATE_TARGETS", "false")
    with pytest.raises(ValidationError):
        asyncio.run(target_policy.validate_target_host("   "))


def test_validate_target_host_accepts_literal_public_ip(monkeypatch):
    monkeypatch.setenv("MONITOR_ALLOW_PRIVATE_TARGETS", "false")
    asyncio.run(target_policy.validate_target_host("8.8.8.8"))
