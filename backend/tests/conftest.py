import base64
import os

import pytest

os.environ.setdefault("APP_NAME", "Orion Uptime Tests")
os.environ.setdefault("APP_VERSION", "0.0.0")
os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("JWT_SECRET", "test-secret-" + "0" * 52)
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("CREDENTIALS_ENCRYPTION_KEY", base64.urlsafe_b64encode(b"\x01" * 32).decode())
os.environ.setdefault("MONITOR_ALLOW_PRIVATE_TARGETS", "false")
os.environ.setdefault("TRUSTED_PROXIES", "")
os.environ.setdefault("DEFAULT_ADMIN_USERNAME", "admin")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("MONITOR_FAILURE_THRESHOLD", "3")
os.environ.setdefault("MONITOR_RECOVERY_THRESHOLD", "2")


@pytest.fixture
def anyio_backend():
    return "asyncio"
