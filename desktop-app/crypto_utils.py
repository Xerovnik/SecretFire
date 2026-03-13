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

import os
import json
import base64
import hashlib
import hmac as hmac_lib
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import (
    Encoding, PublicFormat, PrivateFormat, NoEncryption
)
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


def generate_node_identity():
    x25519_priv = X25519PrivateKey.generate()
    ed25519_priv = Ed25519PrivateKey.generate()

    x25519_priv_bytes = x25519_priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    x25519_pub_bytes = x25519_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ed25519_priv_bytes = ed25519_priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    ed25519_pub_bytes = ed25519_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    return {
        "x25519_private": base64.b64encode(x25519_priv_bytes).decode(),
        "x25519_public": base64.b64encode(x25519_pub_bytes).decode(),
        "ed25519_private": base64.b64encode(ed25519_priv_bytes).decode(),
        "ed25519_public": base64.b64encode(ed25519_pub_bytes).decode(),
        "node_id": base64.b64encode(ed25519_pub_bytes[:16]).decode(),
    }


def derive_session_key(x25519_private_b64, peer_x25519_public_b64):
    priv_bytes = base64.b64decode(x25519_private_b64)
    pub_bytes = base64.b64decode(peer_x25519_public_b64)
    priv_key = X25519PrivateKey.from_private_bytes(priv_bytes)

    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
    pub_key = X25519PublicKey.from_public_bytes(pub_bytes)
    shared = priv_key.exchange(pub_key)

    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"secretfire-session-v1")
    return hkdf.derive(shared)


def generate_broadcast_key():
    return os.urandom(32)


def encrypt_chunk(plaintext: bytes, key: bytes) -> bytes:
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ct


def decrypt_chunk(ciphertext: bytes, key: bytes) -> bytes:
    aesgcm = AESGCM(key)
    nonce = ciphertext[:12]
    ct = ciphertext[12:]
    return aesgcm.decrypt(nonce, ct, None)


def sign_post(content: str, ed25519_private_b64: str) -> str:
    priv_bytes = base64.b64decode(ed25519_private_b64)
    priv_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)
    sig = priv_key.sign(content.encode())
    return base64.b64encode(sig).decode()


def verify_post(content: str, signature_b64: str, ed25519_public_b64: str) -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        pub_bytes = base64.b64decode(ed25519_public_b64)
        sig = base64.b64decode(signature_b64)
        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pub_key.verify(sig, content.encode())
        return True
    except Exception:
        return False


def compute_hmac(data: bytes, key: bytes) -> bytes:
    return hmac_lib.new(key, data, hashlib.sha256).digest()[:8]


def verify_hmac(data: bytes, key: bytes, expected: bytes) -> bool:
    computed = compute_hmac(data, key)
    return hmac_lib.compare_digest(computed, expected)


def random_message_id() -> bytes:
    return os.urandom(16)


def short_id(pubkey_b64: str) -> str:
    raw = base64.b64decode(pubkey_b64)
    return base64.b64encode(raw[:6]).decode().rstrip("=")
