import pytest

from app.service.exceptions import ValidationError
from app.service.target_policy import validate_target_host, validate_target_url

pytestmark = pytest.mark.anyio


async def test_private_targets_rejected_by_default():
    for url in ("http://127.0.0.1/health", "https://10.1.2.3/", "http://169.254.169.254/latest/meta-data", "http://[::1]/"):
        with pytest.raises(ValidationError):
            await validate_target_url(url)
    with pytest.raises(ValidationError):
        await validate_target_host("192.168.1.1")


async def test_private_targets_allowed_when_enabled(monkeypatch):
    monkeypatch.setenv("MONITOR_ALLOW_PRIVATE_TARGETS", "true")
    await validate_target_url("http://127.0.0.1/health")
    await validate_target_host("10.0.0.1")


async def test_public_address_allowed():
    await validate_target_url("https://8.8.8.8/")


async def test_scheme_and_credentials_validation():
    with pytest.raises(ValidationError):
        await validate_target_url("file:///etc/passwd")
    with pytest.raises(ValidationError):
        await validate_target_url("ftp://8.8.8.8/")
    with pytest.raises(ValidationError):
        await validate_target_url("https://user:pass@8.8.8.8/")
    with pytest.raises(ValidationError):
        await validate_target_url("https:///no-host")
