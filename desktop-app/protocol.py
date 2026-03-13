# GhostWire
# Copyright (C) 2026 noxruneshadow
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
GhostWire Message Protocol

Packet format (per fragment):
  [16 bytes] message_id
  [2 bytes]  seq_num (big-endian)
  [2 bytes]  total_parts (big-endian)
  [8 bytes]  timestamp (big-endian unix)
  [8 bytes]  HMAC-SHA256[:8]
  [N bytes]  encrypted payload (CHUNK_SIZE max)
  [padding]  random bytes to fixed packet size

Total wire size: HEADER_SIZE(36) + encrypted_payload
"""

import os
import struct
import time
import base64
import json
from crypto_utils import encrypt_chunk, decrypt_chunk, compute_hmac, verify_hmac, random_message_id, generate_broadcast_key

CHUNK_SIZE = 460
PACKET_SIZE = 512


def _pad_to(data: bytes, target: int) -> bytes:
    if len(data) >= target:
        return data
    return data + os.urandom(target - len(data))


def fragment_message(message: str, session_key: bytes = None) -> tuple[list[bytes], bytes, str]:
    if session_key is None:
        session_key = generate_broadcast_key()

    msg_bytes = message.encode("utf-8")
    chunks = [msg_bytes[i:i + CHUNK_SIZE] for i in range(0, len(msg_bytes), CHUNK_SIZE)]
    if not chunks:
        chunks = [b""]

    msg_id = random_message_id()
    total = len(chunks)
    ts = int(time.time())
    packets = []

    for seq, chunk in enumerate(chunks):
        encrypted_payload = encrypt_chunk(chunk, session_key)

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
    session_key_b64 = base64.b64encode(session_key).decode()
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


def reassemble_fragments(fragments: list[tuple[int, bytes]], session_key: bytes) -> str | None:
    try:
        sorted_frags = sorted(fragments, key=lambda x: x[0])
        chunks = []
        for seq, encrypted_payload in sorted_frags:
            chunk = decrypt_chunk(encrypted_payload, session_key)
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8")
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
