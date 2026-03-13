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
GossipManager — syncs posts and peer lists with known nodes.

In Tor mode: all requests go through the SOCKS5 proxy to .onion addresses.
In demo mode: direct HTTP (for local testing with multiple instances).
"""

import json
import time
import logging
import threading
import hashlib
import base64
import uuid
import requests
import storage
import protocol
import crypto_utils
from config import GOSSIP_INTERVAL, TOR_HIDDEN_SERVICE_PORT

logger = logging.getLogger("gossip")


def _peer_url(onion_address: str) -> str:
    return f"http://{onion_address}"


class GossipManager:
    def __init__(self, tor_manager, node_identity: dict, broadcast_key: bytes):
        self.tor = tor_manager
        self.identity = node_identity
        self.broadcast_key = broadcast_key
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Gossip manager started")

    def stop(self):
        self._stop_event.set()

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self._sync_all_peers()
                self._process_complete_fragments()
            except Exception as e:
                logger.error(f"Gossip loop error: {e}")
            self._stop_event.wait(GOSSIP_INTERVAL)

    def _get_session(self, timeout=15):
        session = requests.Session()
        proxies = self.tor.get_proxies()
        if proxies:
            session.proxies.update(proxies)
        session.timeout = timeout
        return session

    def _sync_all_peers(self):
        peers = storage.get_peers(active_only=True)
        for peer in peers:
            addr = peer["onion_address"]
            if addr in ("demo-mode-no-tor.local", "demo-mode-tor-failed.local", "unknown.onion"):
                continue
            try:
                self._sync_peer(addr)
            except Exception as e:
                logger.debug(f"Failed to sync {addr}: {e}")
                storage.update_peer_status(addr, False)

    def _sync_peer(self, onion_address: str):
        session = self._get_session()
        url = _peer_url(onion_address) + "/api/sync"

        my_post_ids = set(storage.get_post_ids())
        payload = {
            "from": self.tor.onion_address,
            "known_post_ids": list(my_post_ids),
            "broadcast_key": base64.b64encode(self.broadcast_key).decode(),
        }

        resp = session.post(url, json=payload, timeout=20)
        if resp.status_code != 200:
            return

        data = resp.json()

        for peer_addr in data.get("peers", []):
            if peer_addr and peer_addr != self.tor.onion_address:
                storage.save_peer(peer_addr)

        for post in data.get("posts", []):
            pid = post.get("post_id")
            if pid and not storage.post_exists(pid):
                storage.save_post(
                    post_id=pid,
                    content=post["content"],
                    author_pubkey=post.get("author_pubkey"),
                    signature=post.get("signature"),
                    timestamp=post.get("timestamp"),
                    source_peer=onion_address,
                )

        storage.update_peer_status(onion_address, True)
        logger.debug(f"Synced with {onion_address}")

    def broadcast_post(self, post: dict):
        packets, key, msg_id = protocol.fragment_message(
            json.dumps(post), self.broadcast_key
        )
        peers = storage.get_peers(active_only=True)
        session = self._get_session()

        for i, packet in enumerate(packets):
            encoded = protocol.encode_packet_for_wire(packet)
            for peer in peers:
                addr = peer["onion_address"]
                if addr in ("demo-mode-no-tor.local", "demo-mode-tor-failed.local", "unknown.onion"):
                    continue
                try:
                    url = _peer_url(addr) + "/fragment"
                    session.post(url, json={
                        "fragment": encoded,
                        "broadcast_key": base64.b64encode(self.broadcast_key).decode(),
                    }, timeout=10)
                except Exception:
                    pass

    def receive_fragment(self, encoded_fragment: str, broadcast_key_b64: str = None):
        try:
            packet = protocol.decode_packet_from_wire(encoded_fragment)
            h = protocol.parse_packet_header(packet)
            if not h:
                return False

            key = self.broadcast_key
            if broadcast_key_b64:
                try:
                    key = base64.b64decode(broadcast_key_b64)
                except Exception:
                    pass

            if not protocol.verify_packet(packet, key):
                logger.warning("Fragment HMAC verification failed")
                return False

            storage.save_fragment(
                message_id=h["msg_id_b64"],
                seq_num=h["seq_num"],
                total_parts=h["total_parts"],
                encrypted_blob=h["encrypted_payload"],
                session_key=base64.b64encode(key).decode(),
            )
            self._process_complete_fragments()
            return True
        except Exception as e:
            logger.error(f"Fragment receive error: {e}")
            return False

    def _process_complete_fragments(self):
        complete_ids = storage.get_complete_message_ids()
        for msg_id in complete_ids:
            frags = storage.get_fragments(msg_id)
            if not frags:
                continue

            session_key_b64 = frags[0]["session_key"]
            if not session_key_b64:
                continue

            try:
                session_key = base64.b64decode(session_key_b64)
                fragments_list = [(f["seq_num"], bytes(f["encrypted_blob"])) for f in frags]
                message = protocol.reassemble_fragments(fragments_list, session_key)
                if message:
                    try:
                        post = json.loads(message)
                        if "post_id" in post and "content" in post:
                            if not storage.post_exists(post["post_id"]):
                                storage.save_post(
                                    post_id=post["post_id"],
                                    content=post["content"],
                                    author_pubkey=post.get("author_pubkey"),
                                    signature=post.get("signature"),
                                    timestamp=post.get("timestamp"),
                                    source_peer="fragment-reassembly",
                                )
                    except json.JSONDecodeError:
                        pass
                    storage.delete_fragments(msg_id)
            except Exception as e:
                logger.debug(f"Fragment reassembly error for {msg_id}: {e}")

    def handle_sync_request(self, data: dict) -> dict:
        from_peer = data.get("from", "")
        known_ids = set(data.get("known_post_ids", []))
        broadcast_key_b64 = data.get("broadcast_key")

        if from_peer and from_peer != self.tor.onion_address:
            storage.save_peer(from_peer)

        if broadcast_key_b64:
            try:
                new_key = base64.b64decode(broadcast_key_b64)
                if len(new_key) == 32:
                    pass
            except Exception:
                pass

        all_posts = storage.get_posts(limit=100)
        new_posts = [p for p in all_posts if p["id"] not in known_ids]

        peer_list = [p["onion_address"] for p in storage.get_peers(active_only=True)]
        if self.tor.onion_address:
            peer_list.append(self.tor.onion_address)

        return {
            "posts": [{"post_id": p["id"], "content": p["content"],
                       "author_pubkey": p.get("author_pubkey"), "signature": p.get("signature"),
                       "timestamp": p["timestamp"]} for p in new_posts[:50]],
            "peers": peer_list[:20],
        }
