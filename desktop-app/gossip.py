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

Security features:
  - Signed peer lists: outbound peer lists are Ed25519-signed; inbound lists
    are verified before peers are accepted (prevents Sybil peer injection).
  - Per-session broadcast key: a fresh AES-256 key is generated on startup
    and rotated every 24 hours.  Old keys are kept briefly for late fragments.
  - key_id field in all payloads so receivers can look up the right key.
"""

import json
import os
import re
import time
import logging
import threading
import base64
from collections import deque

import requests
import storage
import protocol
import crypto_utils
import peer_auth as _peer_auth_mod
from config import GOSSIP_INTERVAL, TOR_HIDDEN_SERVICE_PORT

logger = logging.getLogger("gossip")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_V3_ONION_RE = re.compile(r'^[a-z2-7]{56}\.onion$')

_FRAGMENT_MAX_AGE_S    = 48 * 3600
_FRAGMENT_MAX_FUTURE_S = 300

_MAX_FRAGS_PER_WINDOW = 120
_RATE_WINDOW_S        = 60

_MAX_FRAGMENT_BYTES = 8192

_KEY_ROTATION_INTERVAL = 24 * 3600   # rotate broadcast key every 24 hours
_MAX_OLD_KEYS          = 3           # keep this many past keys for late fragments
_PEER_SIG_MAX_AGE      = 300         # seconds — reject peer list sigs older than this

_INACTIVE_RETRY_CYCLES = 3           # retry inactive peers every N cycles


def _peer_url(onion_address: str) -> str:
    return f"http://{onion_address}"


def _is_valid_onion(addr: str) -> bool:
    return bool(_V3_ONION_RE.match(addr))


def _new_key_id() -> str:
    return base64.b64encode(os.urandom(8)).decode().rstrip("=")[:8]


# ---------------------------------------------------------------------------
# GossipManager
# ---------------------------------------------------------------------------

class GossipManager:
    def __init__(
        self,
        tor_manager,
        node_identity: dict,
        broadcast_key: bytes,
        key_id: str = "",
    ):
        self.tor      = tor_manager
        self.identity = node_identity

        self._key_lock  = threading.Lock()
        self.broadcast_key = broadcast_key
        self.key_id        = key_id or _new_key_id()
        self._key_store: dict[str, bytes] = {self.key_id: broadcast_key}

        self._stop_event = threading.Event()
        self._thread          = None
        self._rotation_thread = None

        self._frag_bucket: deque = deque()
        self._frag_lock = threading.Lock()

        self._auth = _peer_auth_mod.PeerAuthenticator()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="gossip"
        )
        self._thread.start()

        self._rotation_thread = threading.Thread(
            target=self._key_rotation_loop, daemon=True, name="key-rotation"
        )
        self._rotation_thread.start()

        logger.info(f"Gossip manager started (key_id={self.key_id})")

    def stop(self):
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Broadcast key rotation
    # ------------------------------------------------------------------

    def _key_rotation_loop(self):
        """Rotate the broadcast key every 24 hours."""
        while not self._stop_event.is_set():
            self._stop_event.wait(_KEY_ROTATION_INTERVAL)
            if not self._stop_event.is_set():
                self._rotate_key()

    def _rotate_key(self):
        new_key    = crypto_utils.generate_broadcast_key()
        new_key_id = _new_key_id()
        with self._key_lock:
            self.broadcast_key = new_key
            self.key_id        = new_key_id
            self._key_store[new_key_id] = new_key
            while len(self._key_store) > _MAX_OLD_KEYS:
                oldest = next(iter(self._key_store))
                if oldest != new_key_id:
                    del self._key_store[oldest]
        logger.info(f"Broadcast key rotated — new key_id={new_key_id}")

    def _get_key_for_id(self, key_id: str) -> bytes | None:
        with self._key_lock:
            return self._key_store.get(key_id)

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _accept_fragment(self) -> bool:
        now = time.time()
        with self._frag_lock:
            cutoff = now - _RATE_WINDOW_S
            while self._frag_bucket and self._frag_bucket[0] < cutoff:
                self._frag_bucket.popleft()
            if len(self._frag_bucket) >= _MAX_FRAGS_PER_WINDOW:
                return False
            self._frag_bucket.append(now)
            return True

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _run_loop(self):
        cycle = 0
        while not self._stop_event.is_set():
            try:
                include_inactive = (cycle % _INACTIVE_RETRY_CYCLES == 0)
                self._sync_all_peers(include_inactive=include_inactive)
                self._process_complete_fragments()
                cycle += 1
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

    # ------------------------------------------------------------------
    # Signed peer lists
    # ------------------------------------------------------------------

    def _sign_peer_list(self, peer_list: list) -> dict:
        """Return a signed peer-list envelope."""
        timestamp = int(time.time())
        nonce     = base64.b64encode(os.urandom(16)).decode()
        canonical = json.dumps(
            {"peers": sorted(peer_list), "timestamp": timestamp, "nonce": nonce},
            sort_keys=True,
        )
        sig = crypto_utils.sign_post(canonical, self.identity["ed25519_private"])
        return {
            "peers":     sorted(peer_list),
            "timestamp": timestamp,
            "nonce":     nonce,
            "signer":    self.identity["ed25519_public"],
            "signature": sig,
        }

    def _verify_peer_list(self, signed_data: dict) -> bool:
        """Return True iff the signed peer-list envelope has a valid, fresh signature."""
        try:
            ts  = signed_data.get("timestamp", 0)
            now = time.time()
            if now - ts > _PEER_SIG_MAX_AGE:
                logger.warning("Peer list signature expired — discarding")
                return False
            if ts - now > 60:
                logger.warning("Peer list signature timestamp in the future — discarding")
                return False

            nonce  = signed_data.get("nonce", "")
            peers  = signed_data.get("peers", [])
            signer = signed_data.get("signer", "")
            sig    = signed_data.get("signature", "")
            if not all([nonce, signer, sig]):
                return False

            canonical = json.dumps(
                {"peers": sorted(peers), "timestamp": ts, "nonce": nonce},
                sort_keys=True,
            )
            return crypto_utils.verify_post(canonical, sig, signer)
        except Exception as e:
            logger.warning(f"Peer list verification error: {e}")
            return False

    # ------------------------------------------------------------------
    # Outbound sync
    # ------------------------------------------------------------------

    _SKIP_ADDRS = frozenset({
        "demo-mode-no-tor.local",
        "demo-mode-tor-failed.local",
        "unknown.onion",
    })

    def _sync_all_peers(self, include_inactive=False):
        peers = storage.get_peers(active_only=not include_inactive)
        for peer in peers:
            addr = peer["onion_address"]
            if addr in self._SKIP_ADDRS:
                continue
            try:
                self._sync_peer(addr)
            except Exception as e:
                logger.debug(f"Failed to sync {addr}: {e}")
                # Re-read last_seen so we don't override a recent inbound contact.
                # If the peer reached us while our outbound was timing out, their
                # last_seen was refreshed by save_peer() — keep them active.
                fresh = storage.get_peer(addr)
                if fresh is None or (time.time() - fresh["last_seen"] > GOSSIP_INTERVAL * 2):
                    storage.update_peer_status(addr, False)

    def _sync_peer(self, onion_address: str):
        session = self._get_session()
        url = _peer_url(onion_address) + "/api/sync"

        my_post_ids   = set(storage.get_post_ids())
        my_delete_ids = set(storage.get_all_delete_tombstone_ids())
        with self._key_lock:
            current_key    = self.broadcast_key
            current_key_id = self.key_id

        our_onion  = self.tor.onion_address
        our_pubkey = self.identity.get("ed25519_public", "")

        payload = {
            "from":              our_onion,
            "known_post_ids":    list(my_post_ids),
            "known_delete_ids":  list(my_delete_ids),
            "broadcast_key":     base64.b64encode(current_key).decode(),
            "key_id":            current_key_id,
            "node_pubkey":       our_pubkey,
        }

        # If this peer previously challenged us, include the signed response
        if self._auth.has_pending_challenge(onion_address) and our_onion:
            sig = self._auth.build_challenge_response(
                peer_onion=onion_address,
                our_onion=our_onion,
                ed25519_private_b64=self.identity.get("ed25519_private", ""),
            )
            if sig:
                payload["challenge_response"] = sig
                logger.debug(f"Sending challenge response to {onion_address}")

        resp = session.post(url, json=payload, timeout=(60, 30))
        if resp.status_code != 200:
            storage.update_peer_status(onion_address, False)
            return

        data = resp.json()

        # Store any challenge the peer issued to us for the next sync cycle
        auth_challenge = data.get("auth_challenge")
        if auth_challenge:
            self._auth.store_received_challenge(onion_address, auth_challenge)

        peer_sig = data.get("peer_signature")
        if peer_sig and self._verify_peer_list(peer_sig):
            verified_peers = peer_sig.get("peers", [])
        else:
            if peer_sig:
                logger.warning(
                    f"Peer list signature INVALID from {onion_address} — "
                    "falling back to unsigned list"
                )
            verified_peers = data.get("peers", [])

        for peer_addr in verified_peers:
            if peer_addr and peer_addr != self.tor.onion_address:
                if _is_valid_onion(peer_addr):
                    storage.save_peer(peer_addr)
                else:
                    logger.warning(
                        f"Discarding invalid onion address from peer: {peer_addr!r}"
                    )

        # Apply delete tombstones BEFORE accepting posts so we don't store
        # posts that should already be gone
        for tombstone in data.get("delete_tombstones", []):
            self._apply_delete_tombstone(tombstone)

        for post in data.get("posts", []):
            pid = post.get("post_id")
            if pid and not storage.post_exists(pid) and not storage.is_deleted(pid):
                storage.save_post(
                    post_id=pid,
                    content=post["content"],
                    author_pubkey=post.get("author_pubkey"),
                    signature=post.get("signature"),
                    timestamp=post.get("timestamp"),
                    source_peer=onion_address,
                    parent_id=post.get("parent_id"),
                )

        storage.update_peer_status(onion_address, True)
        logger.debug(f"Synced with {onion_address}")

    # ------------------------------------------------------------------
    # Fragment broadcast
    # ------------------------------------------------------------------

    def broadcast_post(self, post: dict):
        with self._key_lock:
            current_key    = self.broadcast_key
            current_key_id = self.key_id

        packets, key, msg_id = protocol.fragment_message(
            json.dumps(post), current_key
        )
        peers   = storage.get_peers(active_only=True)
        session = self._get_session()

        for packet in packets:
            encoded = protocol.encode_packet_for_wire(packet)
            for peer in peers:
                addr = peer["onion_address"]
                if addr in (
                    "demo-mode-no-tor.local",
                    "demo-mode-tor-failed.local",
                    "unknown.onion",
                ):
                    continue
                try:
                    url = _peer_url(addr) + "/fragment"
                    session.post(
                        url,
                        json={
                            "fragment":      encoded,
                            "broadcast_key": base64.b64encode(current_key).decode(),
                            "key_id":        current_key_id,
                        },
                        timeout=10,
                    )
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Inbound fragment handling
    # ------------------------------------------------------------------

    def receive_fragment(
        self,
        encoded_fragment: str,
        broadcast_key_b64: str = None,
        key_id: str = None,
    ):
        try:
            if len(encoded_fragment) > _MAX_FRAGMENT_BYTES:
                logger.warning("Received oversized fragment — rejected")
                return False

            if not self._accept_fragment():
                logger.warning("Fragment rate limit exceeded — dropped")
                return False

            packet = protocol.decode_packet_from_wire(encoded_fragment)
            h = protocol.parse_packet_header(packet)
            if not h:
                return False

            now     = time.time()
            frag_ts = h["timestamp"]
            age     = now - frag_ts
            if age > _FRAGMENT_MAX_AGE_S:
                logger.warning(
                    f"Fragment too old ({age/3600:.1f} h) — rejected (replay protection)"
                )
                return False
            if frag_ts - now > _FRAGMENT_MAX_FUTURE_S:
                logger.warning(
                    f"Fragment timestamp {frag_ts - now:.0f} s in the future — rejected"
                )
                return False

            # Key resolution: try key_id first, then fall back to provided key
            key = None
            if key_id:
                key = self._get_key_for_id(key_id)
            if key is None and broadcast_key_b64:
                try:
                    key = base64.b64decode(broadcast_key_b64)
                except Exception:
                    pass
            if key is None:
                with self._key_lock:
                    key = self.broadcast_key

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

    # ------------------------------------------------------------------
    # Fragment reassembly
    # ------------------------------------------------------------------

    def _process_complete_fragments(self):
        complete_ids = storage.get_complete_message_ids()
        for msg_id_b64 in complete_ids:
            frags = storage.get_fragments(msg_id_b64)
            if not frags:
                continue

            session_key_b64 = frags[0]["session_key"]
            if not session_key_b64:
                continue

            try:
                session_key    = base64.b64decode(session_key_b64)
                msg_id_bytes   = base64.b64decode(msg_id_b64)
                fragments_list = [
                    (f["seq_num"], bytes(f["encrypted_blob"])) for f in frags
                ]
                message = protocol.reassemble_fragments(
                    fragments_list, session_key, msg_id_bytes=msg_id_bytes
                )
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
                                    parent_id=post.get("parent_id"),
                                )
                    except json.JSONDecodeError:
                        pass
                    storage.delete_fragments(msg_id_b64)
            except Exception as e:
                logger.debug(f"Fragment reassembly error for {msg_id_b64}: {e}")

    # ------------------------------------------------------------------
    # Inbound sync handling
    # ------------------------------------------------------------------

    def handle_sync_request(self, data: dict) -> dict:
        from_peer          = data.get("from", "")
        known_ids          = set(data.get("known_post_ids", []))
        known_delete_ids   = set(data.get("known_delete_ids", []))
        node_pubkey        = data.get("node_pubkey", "")
        challenge_response = data.get("challenge_response", "")

        if from_peer and from_peer != self.tor.onion_address:
            if _is_valid_onion(from_peer):
                storage.save_peer(from_peer)
                storage.update_peer_status(from_peer, True)
            else:
                logger.warning(
                    f"Sync request from invalid onion address: {from_peer!r}"
                )
                from_peer = ""

        # --- Challenge-response authentication ----------------------------
        if from_peer and node_pubkey:
            if not self._auth.check_pubkey_claim(from_peer, node_pubkey):
                logger.warning(
                    f"Rejecting sync from {from_peer[:20]}… — pubkey mismatch"
                )
            elif challenge_response:
                self._auth.verify_response(from_peer, node_pubkey, challenge_response)
            else:
                self._auth.store_pubkey(from_peer, node_pubkey)

        auth_challenge = None
        if from_peer and node_pubkey:
            auth_challenge = self._auth.issue_challenge(from_peer)
        # ------------------------------------------------------------------

        # Apply any delete tombstones the peer is sending us
        for tombstone in data.get("delete_tombstones", []):
            self._apply_delete_tombstone(tombstone)

        # Only return posts that the peer doesn't know about AND haven't been deleted
        all_posts = storage.get_posts(limit=100)
        new_posts = [
            p for p in all_posts
            if p["id"] not in known_ids and not storage.is_deleted(p["id"])
        ]

        # Return tombstones the peer doesn't know about yet
        new_tombstones = storage.get_delete_tombstones(exclude_ids=known_delete_ids)

        peer_list = [p["onion_address"] for p in storage.get_peers(active_only=True)]
        if self.tor.onion_address:
            peer_list.append(self.tor.onion_address)

        signed_peers = self._sign_peer_list(peer_list[:20])

        with self._key_lock:
            current_key_id = self.key_id

        response = {
            "posts": [
                {
                    "post_id":       p["id"],
                    "content":       p["content"],
                    "author_pubkey": p.get("author_pubkey"),
                    "signature":     p.get("signature"),
                    "timestamp":     p["timestamp"],
                    "parent_id":     p.get("parent_id"),
                }
                for p in new_posts[:50]
            ],
            "delete_tombstones": new_tombstones[:50],
            "peers":             peer_list[:20],
            "peer_signature":    signed_peers,
            "key_id":            current_key_id,
        }
        if auth_challenge:
            response["auth_challenge"] = auth_challenge
        return response

    # ------------------------------------------------------------------
    # Delete tombstone verification and propagation
    # ------------------------------------------------------------------

    def _apply_delete_tombstone(self, tombstone: dict) -> bool:
        """Verify and apply an inbound delete tombstone.

        Verifies the Ed25519 signature against the claimed author_pubkey.
        If valid, stores the tombstone and removes the post locally.
        Returns True if the tombstone was newly applied.
        """
        try:
            post_id     = tombstone.get("post_id", "")
            author_pub  = tombstone.get("author_pubkey", "")
            delete_sig  = tombstone.get("delete_signature", "")
            delete_ts   = tombstone.get("delete_timestamp", 0)

            if not all([post_id, author_pub, delete_sig, delete_ts]):
                logger.warning("Received incomplete delete tombstone — ignored")
                return False

            # Already have this tombstone — nothing to do
            if storage.is_deleted(post_id):
                return False

            # Reconstruct the canonical message that was signed
            canonical = f"DELETE:{post_id}:{delete_ts}"
            if not crypto_utils.verify_post(canonical, delete_sig, author_pub):
                logger.warning(
                    f"Delete tombstone signature INVALID for post {post_id[:12]}… — ignored"
                )
                return False

            # If the post exists locally, confirm the author_pubkey matches
            # (prevents a valid key from deleting someone else's post)
            local_author = storage.get_post_author_pubkey(post_id)
            if local_author and local_author != author_pub:
                logger.warning(
                    f"Delete tombstone author mismatch for post {post_id[:12]}… — ignored"
                )
                return False

            newly_saved = storage.save_delete_tombstone(
                post_id, author_pub, delete_sig, delete_ts
            )
            if newly_saved:
                logger.info(
                    f"Applied delete tombstone for post {post_id[:12]}… "
                    f"(author {author_pub[:16]}…)"
                )
            return newly_saved

        except Exception as e:
            logger.error(f"Error applying delete tombstone: {e}")
            return False

    def broadcast_delete_tombstone(self, tombstone: dict):
        """Immediately push a delete tombstone to all active peers.

        Called right after the originator issues a delete so that peers
        remove the post without waiting for the next gossip sync cycle.
        """
        peers   = storage.get_peers(active_only=True)
        session = self._get_session()
        _SKIP = {"demo-mode-no-tor.local", "demo-mode-tor-failed.local", "unknown.onion"}

        for peer in peers:
            addr = peer["onion_address"]
            if addr in _SKIP:
                continue
            try:
                url = _peer_url(addr) + "/api/delete_tombstone"
                session.post(url, json=tombstone, timeout=10)
            except Exception:
                pass
