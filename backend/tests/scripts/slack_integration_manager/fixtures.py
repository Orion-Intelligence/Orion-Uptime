from __future__ import annotations

import pytest

from orion.services.encryption_manager.secrets import secret_box


@pytest.fixture
def slack_crypto(monkeypatch):
    monkeypatch.setattr(secret_box, "encrypt_mapping", lambda values: values["webhook_url"])
    monkeypatch.setattr(secret_box, "decrypt_mapping", lambda encrypted: {"webhook_url": encrypted})
