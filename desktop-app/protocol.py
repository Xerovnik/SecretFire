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
SecretFire Message Protocol

Packet format (per fragment):
  [16 bytes] message_id
  [2 bytes]  seq_num (big-endian)
  [2 bytes]  total_parts (big-endian)
  [8 bytes]  timestamp (big-endian unix)
  [8 bytes]  HMAC-SHA256[:8]
  [N bytes]  encrypted payload (CHUNK_SIZE max)

AES-GCM AAD:
  Each encrypted payload is authenticated with the associated data:
    msg_id (16 bytes) | seq_num (2 bytes, big-endian) | total_parts (2 bytes)
  This binds the ciphertext cryptographically to the fragment's position,
  preventing reordering or splicing attacks on individual fragments.

Message padding (traffic analysis resistance):
  Before fragmentation the plaintext is padded to the next fixed bucket size
  (256, 512, 1024, 2048, or 4096 bytes) using random bytes.  The last 2 bytes
  store the original length as a big-endian uint16, allowing exact recovery
  after reassembly.  This makes it significantly harder for a passive observer
  to infer message content from ciphertext length.
"""

import os
import struct
import time
import base64
import json
from crypto_utils import encrypt_chunk, decrypt_chunk, compute_hmac, verify_hmac, random_message_id, generate_broadcast_key

CHUNK_SIZE = 460
PACKET_SIZE = 512

# Fixed bucket sizes for message-level padding (bytes).
# The 2-byte length footer is included in the budget.
_PAD_BUCKETS = (256, 512, 1024, 2048, 4096)


# ---------------------------------------------------------------------------
# Message-level padding
# ---------------------------------------------------------------------------

def _pad_message(data: bytes) -> bytes:
    """Pad plaintext to the next fixed bucket size using random bytes.

    Layout: [original data] [random padding] [2-byte big-endian original length]

    If the data is larger than all buckets (very long message), a zero-length
    sentinel is appended so unpadding always works correctly.
    """
    orig_len = len(data)
    target = next((b for b in _PAD_BUCKETS if b >= orig_len + 2), None)
    if target is None:
        return data + struct.pack(">H", 0)
    pad_len = target - orig_len - 2
    return data + os.urandom(pad_len) + struct.pack(">H", orig_len)


def _unpad_message(data: bytes) -> bytes:
    """Strip padding added by _pad_message and return the original bytes."""
    if len(data) < 2:
        return data
    orig_len = struct.unpack(">H", data[-2:])[0]
    if orig_len == 0:
        return data[:-2]
    if orig_len > len(data) - 2:
        return data
    return data[:orig_len]


# ---------------------------------------------------------------------------
# Fragment helpers
# ---------------------------------------------------------------------------

def _fragment_aad(msg_id: bytes, seq: int, total: int) -> bytes:
    """Build the associated data that binds a ciphertext to its position."""
    return msg_id + struct.pack(">H", seq) + struct.pack(">H", total)


def _pad_to(data: bytes, target: int) -> bytes:
    if len(data) >= target:
        return data
    return data + os.urandom(target - len(data))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fragment_message(message: str, session_key: bytes = None) -> tuple[list[bytes], bytes, str]:
    if session_key is None:
        session_key = generate_broadcast_key()

    msg_bytes = _pad_message(message.encode("utf-8"))
    chunks = [msg_bytes[i:i + CHUNK_SIZE] for i in range(0, len(msg_bytes), CHUNK_SIZE)]
    if not chunks:
        chunks = [b""]

    msg_id = random_message_id()
    total = len(chunks)
    ts = int(time.time())
    packets = []

    for seq, chunk in enumerate(chunks):
        aad = _fragment_aad(msg_id, seq, total)
        encrypted_payload = encrypt_chunk(chunk, session_key, aad=aad)

        header = (
            msg_id
            + struct.pack(">H", seq)
            + struct.pack(">H", total)
            + struct.pack(">Q", ts)
        )
        hmac_val = compute_hmac(header + encrypted_payload, session_key)
        packet = header + hmac_val + encrypted_payload
        packets.append(packet)

    msg_id_b64 = base64.b64encode(msg_id).decode()
    return packets, session_key, msg_id_b64


def parse_packet_header(packet: bytes) -> dict | None:
    try:
        msg_id = packet[:16]
        seq_num = struct.unpack(">H", packet[16:18])[0]
        total_parts = struct.unpack(">H", packet[18:20])[0]
        timestamp = struct.unpack(">Q", packet[20:28])[0]
        hmac_val = packet[28:36]
        encrypted_payload = packet[36:]
        return {
            "msg_id": msg_id,
            "msg_id_b64": base64.b64encode(msg_id).decode(),
            "seq_num": seq_num,
            "total_parts": total_parts,
            "timestamp": timestamp,
            "hmac_val": hmac_val,
            "encrypted_payload": encrypted_payload,
        }
    except Exception:
        return None


def verify_packet(packet: bytes, session_key: bytes) -> bool:
    h = parse_packet_header(packet)
    if not h:
        return False
    header = packet[:28]
    payload = packet[36:]
    expected_hmac = h["hmac_val"]
    return verify_hmac(header + payload, session_key, expected_hmac)


def reassemble_fragments(
    fragments: list[tuple[int, bytes]],
    session_key: bytes,
    msg_id_bytes: bytes = None,
) -> str | None:
    """Decrypt, reassemble, and unpad ordered fragments.

    msg_id_bytes must be the raw 16-byte message ID when AAD is in use.
    Pass None only when processing legacy fragments without AAD.
    """
    try:
        sorted_frags = sorted(fragments, key=lambda x: x[0])
        total = len(sorted_frags)
        chunks = []
        for seq, encrypted_payload in sorted_frags:
            aad = _fragment_aad(msg_id_bytes, seq, total) if msg_id_bytes is not None else None
            chunk = decrypt_chunk(encrypted_payload, session_key, aad=aad)
            chunks.append(chunk)
        raw = b"".join(chunks)
        return _unpad_message(raw).decode("utf-8")
    except Exception:
        return None


def encode_packet_for_wire(packet: bytes) -> str:
    return base64.b64encode(packet).decode()


def decode_packet_from_wire(encoded: str) -> bytes:
    return base64.b64decode(encoded)


def make_post_envelope(post_id: str, content: str, author_pubkey: str, signature: str, timestamp: int) -> dict:
    return {
        "post_id": post_id,
        "content": content,
        "author_pubkey": author_pubkey,
        "signature": signature,
        "timestamp": timestamp,
    }
