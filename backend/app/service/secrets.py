import json
import os

from cryptography.fernet import Fernet
from dotenv import load_dotenv

ENCRYPTION_KEY_ENV = "CREDENTIALS_ENCRYPTION_KEY"


class SecretBox:
    def __init__(self) -> None:
        self._fernet: Fernet | None = None

    def encrypt_mapping(self, values: dict[str, str]) -> str:
        payload = json.dumps(values, separators=(",", ":")).encode()
        return self._cipher().encrypt(payload).decode()

    def decrypt_mapping(self, token: str) -> dict[str, str]:
        return json.loads(self._cipher().decrypt(token.encode()))

    def _cipher(self) -> Fernet:
        if self._fernet is None:
            load_dotenv()
            key = os.environ.get(ENCRYPTION_KEY_ENV, "").strip()
            if not key:
                raise RuntimeError(
                    f"{ENCRYPTION_KEY_ENV} is not configured. Generate one with: "
                    "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                )
            self._fernet = Fernet(key.encode())
        return self._fernet

secret_box = SecretBox()
