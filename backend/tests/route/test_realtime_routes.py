from __future__ import annotations


def test_stream_events_emits_initial_snapshot(client, as_admin, stub_stream):
    response = client.get("/api/events")
    assert response.status_code == 200
    assert "event: snapshot" in response.text


def test_stream_events_requires_authentication(client):
    response = client.get("/api/events")
    assert response.status_code == 401
