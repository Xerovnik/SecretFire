# SecretFire
# Copyright (C) 2026 J. Zerovnik
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
SecretFire Identity Manager

Stores the Ed25519/X25519 keypair encrypted at rest using:
  Argon2id (key derivation from password) + AES-256-GCM (encryption)

On-disk format:
  [16 bytes]  Argon2id salt (random, not secret)
  [12 bytes]  AES-GCM nonce (random per save)
  [N  bytes]  AES-GCM ciphertext  (JSON payload + 16-byte GCM auth tag)

The JSON payload holds all key material and is decrypted once at startup,
held in memory only, and never written back to disk in plaintext.
"""

import os
import json
import logging
from pathlib import Path

from argon2.low_level import hash_secret_raw, Type as Argon2Type
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("identity")

# -- Format constants -------------------------------------------------------
_SALT_LEN  = 16
_NONCE_LEN = 12
_KEY_LEN   = 32

# Argon2id tuning — targets ~0.5 s on modest desktop hardware.
# Increase time_cost / memory_cost for stronger protection in future releases.
_TIME_COST   = 3
_MEMORY_COST = 65536   # KiB = 64 MiB
_PARALLELISM = 4


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from a password using Argon2id."""
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=_TIME_COST,
        memory_cost=_MEMORY_COST,
        parallelism=_PARALLELISM,
        hash_len=_KEY_LEN,
        type=Argon2Type.ID,
    )


# ---------------------------------------------------------------------------
# IdentityManager
# ---------------------------------------------------------------------------

class IdentityManager:
    """
    Manages encrypted storage of the node's long-term keypair.

    Typical startup flow:
      mgr = IdentityManager(DATA_DIR)
      if mgr.has_encrypted_identity():
          identity = mgr.load_identity(password)
      else:
          identity = mgr.create_identity(password)
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.identity_file = data_dir / "identity.enc"
        self._identity: dict | None = None

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def has_encrypted_identity(self) -> bool:
        return self.identity_file.exists()

    # ------------------------------------------------------------------
    # Encryption helpers
    # ------------------------------------------------------------------

    def _encrypt(self, identity: dict, password: str) -> bytes:
        salt  = os.urandom(_SALT_LEN)
        key   = _derive_key(password, salt)
        nonce = os.urandom(_NONCE_LEN)
        payload = json.dumps(identity).encode("utf-8")
        ct = AESGCM(key).encrypt(nonce, payload, None)
        return salt + nonce + ct

    def _decrypt(self, data: bytes, password: str) -> dict:
        salt  = data[:_SALT_LEN]
        nonce = data[_SALT_LEN : _SALT_LEN + _NONCE_LEN]
        ct    = data[_SALT_LEN + _NONCE_LEN :]
        key   = _derive_key(password, salt)
        try:
            payload = AESGCM(key).decrypt(nonce, ct, None)
        except Exception:
            raise ValueError("Incorrect password or corrupted identity file")
        return json.loads(payload.decode("utf-8"))

    def _save(self, identity: dict, password: str) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        encrypted = self._encrypt(identity, password)
        self.identity_file.write_bytes(encrypted)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_identity(self, password: str) -> dict:
        """Generate a fresh keypair, encrypt it, and persist to disk."""
        from crypto_utils import generate_node_identity
        identity = generate_node_identity()
        self._save(identity, password)
        self._identity = identity
        logger.info(f"Created new encrypted identity: {identity.get('node_id')}")
        return identity

    def migrate_legacy(self, legacy_identity: dict, password: str) -> dict:
        """Encrypt an existing plaintext identity and persist to disk."""
        self._save(legacy_identity, password)
        self._identity = legacy_identity
        logger.info(
            f"Migrated legacy identity to encrypted storage: "
            f"{legacy_identity.get('node_id')}"
        )
        return legacy_identity

    def load_identity(self, password: str) -> dict:
        """Decrypt and return the stored identity. Raises ValueError on bad password."""
        if not self.identity_file.exists():
            raise FileNotFoundError("No encrypted identity found")
        data = self.identity_file.read_bytes()
        identity = self._decrypt(data, password)
        self._identity = identity
        logger.info(f"Loaded encrypted identity: {identity.get('node_id')}")
        return identity

    @property
    def identity(self) -> dict | None:
        return self._identity
