from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from orion.constants.constant import Paths
from routes import frontend_routes, user_account_routes
from tests.model.fakes import FakeService


def test_health_reports_degraded_without_scheduler(client):
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_protected_route_requires_authentication(client):
    response = client.get("/api/users/list")
    assert response.status_code == 401


def test_protected_route_rejects_insufficient_role(client, override, as_viewer):
    override(user_account_routes.get_user_service, lambda: FakeService(list_users=[]))
    response = client.get("/api/users/list")
    assert response.status_code == 403


def test_unknown_api_route_returns_404(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404


def test_frontend_serves_index_and_static_assets(client, tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "ANGULAR_BUILD", tmp_path)
    (tmp_path / "index.html").write_text("<html>orion</html>", encoding="utf-8")
    (tmp_path / "main.js").write_text("console.log('orion')", encoding="utf-8")

    assert client.get("/index.html").status_code == 200
    assert client.get("/main.js").status_code == 200
    assert client.get("/dashboard").status_code == 200


def test_frontend_rejects_directory_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "ANGULAR_BUILD", tmp_path)
    (tmp_path / "index.html").write_text("<html>orion</html>", encoding="utf-8")

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(frontend_routes.serve_frontend("../secret"))
    assert excinfo.value.status_code == 404


def test_frontend_missing_build_returns_404(client, tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "ANGULAR_BUILD", tmp_path / "missing")
    response = client.get("/dashboard")
    assert response.status_code == 404
