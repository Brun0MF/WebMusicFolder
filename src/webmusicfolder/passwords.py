"""Login password: the environment value until it is changed in the UI, then a stored hash."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

PASSWORD_FILE_NAME = "password.json"
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 200
# scrypt cost: about 16 MiB and tens of milliseconds, fine for a login form.
_N, _R, _P = 2**14, 8, 1


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)


class PasswordStore:
    def __init__(self, path: Path, env_password: str) -> None:
        self.path = Path(path)
        self._env_password = env_password

    def _load(self) -> dict | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            bytes.fromhex(data["salt"])
            bytes.fromhex(data["hash"])
            return data
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @property
    def version(self) -> str:
        """Changes whenever the password changes; sessions made earlier stop being valid."""
        data = self._load()
        return data["version"] if data else ""

    def verify(self, supplied: str) -> bool:
        data = self._load()
        if data is None:
            return hmac.compare_digest(supplied.encode(), self._env_password.encode())
        expected = bytes.fromhex(data["hash"])
        return hmac.compare_digest(_hash(supplied, bytes.fromhex(data["salt"])), expected)

    def set(self, new_password: str) -> str:
        """Store a new password atomically (mode 0600) and return the new version."""
        salt = os.urandom(16)
        version = secrets.token_hex(8)
        payload = {"salt": salt.hex(), "hash": _hash(new_password, salt).hex(), "version": version}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)
        return version
