from __future__ import annotations

import json

import pytest

from orion.services.encryption_manager.secrets import secret_box


@pytest.fixture(autouse=True)
def auth_crypto(monkeypatch):
    monkeypatch.setattr(secret_box, "encrypt_mapping", lambda values: json.dumps(values))
    monkeypatch.setattr(secret_box, "decrypt_mapping", json.loads)
