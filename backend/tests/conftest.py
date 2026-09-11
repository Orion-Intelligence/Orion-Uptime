from __future__ import annotations

import os

os.environ.setdefault("APP_NAME", "Orion Uptime")
os.environ.setdefault("APP_VERSION", "1.0.0")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-value-0123456789abcdef")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")

# Importing the application entrypoint wires the full module graph (routes, managers,
# the monitoring engine, middleware). Those packages are namespace packages, so coverage
# cannot discover them by walking `source`; importing here ensures every backend module is
# loaded and therefore measured, giving an honest full-codebase coverage denominator.
import main  # noqa: E402,F401
