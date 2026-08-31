#!/usr/bin/env python3
"""Write the root .env file used by the CI workflows.

When the ENV_FILE secret is provided it is written verbatim. Otherwise a throwaway
development configuration is derived from template-env with freshly generated
secrets, so the pipeline also runs on forks and pull requests that cannot read
repository secrets.

Set CI_ENV_OUTPUT to write the file somewhere other than <repo>/.env.
"""

from __future__ import annotations

import base64
import os
import pathlib
from secrets import token_bytes, token_urlsafe

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "template-env"
TARGET = pathlib.Path(os.environ.get("CI_ENV_OUTPUT") or ROOT / ".env")


def mask(value: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{value}")


def generated_values() -> dict[str, str]:
    return {
        "APP_ENV": "development",
        "MONGO_ROOT_PASSWORD": token_urlsafe(24),
        "MONGO_APP_PASSWORD": token_urlsafe(24),
        "JWT_SECRET": token_urlsafe(48),
        "CREDENTIALS_ENCRYPTION_KEY": base64.urlsafe_b64encode(
            token_bytes(32)
        ).decode(),
        "DEFAULT_ADMIN_PASSWORD": token_urlsafe(18),
    }


def main() -> int:
    provided = os.environ.get("ENV_FILE", "")
    if provided.strip():
        TARGET.write_text(provided.rstrip("\n") + "\n", encoding="utf-8")
        print(f"Wrote {TARGET} from the ENV_FILE secret")
        return 0

    values = generated_values()
    lines: list[str] = []
    seen: set[str] = set()
    for raw in TEMPLATE.read_text(encoding="utf-8").splitlines():
        key, separator, _ = raw.partition("=")
        key = key.strip()
        if separator and key in values:
            lines.append(f'{key}="{values[key]}"')
            seen.add(key)
        else:
            lines.append(raw)
    for key, value in values.items():
        if key not in seen:
            lines.append(f'{key}="{value}"')

    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for key, value in values.items():
        if key != "APP_ENV":
            mask(value)
    print(f"Wrote {TARGET} from template-env with generated secrets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
