import pytest
from cryptography.fernet import InvalidToken

from app.service.secrets import SecretBox


def test_round_trip():
    box = SecretBox()
    token = box.encrypt_mapping({"username": "u", "password": "p"})
    assert token != '{"username":"u","password":"p"}'
    assert box.decrypt_mapping(token) == {"username": "u", "password": "p"}


def test_tampered_token_rejected():
    box = SecretBox()
    token = box.encrypt_mapping({"k": "v"})
    with pytest.raises(InvalidToken):
        box.decrypt_mapping(token[:-2] + "AA")


def test_missing_key_fails_clearly(monkeypatch):
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", "")
    with pytest.raises(RuntimeError, match="CREDENTIALS_ENCRYPTION_KEY"):
        SecretBox().encrypt_mapping({"k": "v"})
