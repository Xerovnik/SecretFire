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
Challenge-response peer authenticator for SecretFire.

When a peer contacts us (inbound) or we contact them (outbound), a 32-byte
random nonce is issued as a challenge.  The challenged node must return an
Ed25519 signature proving it holds the private key matching the public key it
advertised in signed peer lists.

Challenge message format (signed as a JSON string for compatibility with the
existing sign_post / verify_post interface):

    json.dumps({"challenge": <nonce_b64>, "peer": <responder_onion>},
               sort_keys=True)

Binding the responder's onion address into the signed message prevents a
challenge issued for one session from being replayed in a different context.

Lifecycle per peer:
  1. Peer announces pubkey in first sync request.
  2. We issue a challenge nonce, return it in the sync response.
  3. Peer signs the challenge in its next sync request.
  4. We verify; on success, the pubkey is locked in the DB as auth_pubkey
     and auth_verified is set to 1.
  5. Future connections from the same onion address using a DIFFERENT pubkey
     are rejected with a warning.

Non-blocking: authentication failure never prevents the gossip sync from
completing.  Unauthenticated peers stay in the DB but remain unverified.
"""

import json
import os
import time
import base64
import logging
import threading

import crypto_utils
import storage

logger = logging.getLogger("peer_auth")

_CHALLENGE_BYTES = 32
_CHALLENGE_TTL   = 300    # seconds — unverified challenges expire after 5 min


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _b64d(s: str) -> bytes:
    return base64.b64decode(s)


def _challenge_message(nonce_b64: str, peer_onion: str) -> str:
    """Canonical JSON string that the responder must sign."""
    return json.dumps(
        {"challenge": nonce_b64, "peer": peer_onion},
        sort_keys=True,
    )


class PeerAuthenticator:
    """
    Thread-safe challenge-response manager.

    Two roles:
      Responder — we issue challenges to peers connecting to us (inbound).
      Initiator — we receive challenges from peers we connect to (outbound).
    """

    def __init__(self):
        self._lock = threading.Lock()
        # Challenges we issued: {onion_address: (nonce_bytes, issued_at)}
        self._issued: dict[str, tuple[bytes, float]] = {}
        # Challenges we received: {onion_address: nonce_bytes}
        self._received: dict[str, bytes] = {}

    # ------------------------------------------------------------------
    # Responder side — we issue challenges to incoming peers
    # ------------------------------------------------------------------

    def issue_challenge(self, onion_address: str) -> str:
        """
        Generate a fresh 32-byte nonce for this peer and remember it.
        Returns base64-encoded nonce to send in the sync response.
        """
        nonce = os.urandom(_CHALLENGE_BYTES)
        with self._lock:
            self._issued[onion_address] = (nonce, time.time())
        logger.debug(f"Issued challenge to {onion_address}")
        return _b64e(nonce)

    def verify_response(
        self,
        onion_address: str,
        pubkey_b64: str,
        response_b64: str,
    ) -> bool:
        """
        Verify the challenge response from a peer.

        Returns True if:
          - We have a non-expired challenge for this peer
          - The signature is a valid Ed25519 sig over the challenge message
          - The pubkey matches what was previously stored (if any)

        On success, marks the peer as auth_verified in the DB and locks the
        pubkey so future impersonation attempts are detected.
        On failure, logs a warning and returns False.
        """
        with self._lock:
            entry = self._issued.get(onion_address)
            if not entry:
                logger.warning(
                    f"No pending challenge for {onion_address} — "
                    "ignoring response"
                )
                return False
            nonce, issued_at = entry
            if time.time() - issued_at > _CHALLENGE_TTL:
                del self._issued[onion_address]
                logger.warning(
                    f"Challenge for {onion_address} expired ({_CHALLENGE_TTL}s) — "
                    "peer must re-authenticate"
                )
                return False

        # Check for pubkey mismatch against stored key
        existing = storage.get_peer_auth(onion_address)
        if existing and existing.get("auth_pubkey"):
            stored_pk = existing["auth_pubkey"]
            if stored_pk != pubkey_b64:
                logger.warning(
                    f"Pubkey MISMATCH for {onion_address}: stored={stored_pk[:16]}… "
                    f"claimed={pubkey_b64[:16]}… — possible impersonation, rejecting"
                )
                return False

        nonce_b64 = _b64e(nonce)
        msg = _challenge_message(nonce_b64, onion_address)
        ok = crypto_utils.verify_post(msg, response_b64, pubkey_b64)

        if ok:
            with self._lock:
                self._issued.pop(onion_address, None)
            storage.set_peer_auth(onion_address, pubkey_b64, verified=True)
            logger.info(f"Peer {onion_address[:20]}… authenticated — pubkey locked")
        else:
            logger.warning(
                f"Challenge response INVALID from {onion_address[:20]}…"
            )

        return ok

    def check_pubkey_claim(self, onion_address: str, pubkey_b64: str) -> bool:
        """
        Returns False if this peer was previously authenticated with a
        DIFFERENT pubkey (likely impersonation).  Returns True otherwise.
        """
        existing = storage.get_peer_auth(onion_address)
        if not existing or not existing.get("auth_pubkey"):
            return True
        if existing.get("auth_verified") and existing["auth_pubkey"] != pubkey_b64:
            logger.warning(
                f"Pubkey claim mismatch for verified peer {onion_address[:20]}…: "
                f"stored={existing['auth_pubkey'][:16]}… "
                f"claimed={pubkey_b64[:16]}… — rejecting"
            )
            return False
        return True

    def store_pubkey(self, onion_address: str, pubkey_b64: str) -> None:
        """Persist the claimed pubkey without marking as verified yet."""
        storage.set_peer_auth(onion_address, pubkey_b64, verified=False)

    # ------------------------------------------------------------------
    # Initiator side — we received a challenge, sign it on next sync
    # ------------------------------------------------------------------

    def store_received_challenge(
        self, onion_address: str, challenge_b64: str
    ) -> None:
        """Store a challenge issued to us by `onion_address` for signing."""
        try:
            nonce = _b64d(challenge_b64)
        except Exception:
            logger.warning(
                f"Received malformed challenge nonce from {onion_address}"
            )
            return
        with self._lock:
            self._received[onion_address] = nonce
        logger.debug(f"Stored challenge from {onion_address} for next sync")

    def build_challenge_response(
        self,
        peer_onion: str,
        our_onion: str,
        ed25519_private_b64: str,
    ) -> str | None:
        """
        Sign and consume the stored challenge from `peer_onion`.
        Returns base64 signature, or None if no challenge is pending.
        """
        with self._lock:
            nonce = self._received.pop(peer_onion, None)
        if nonce is None:
            return None
        nonce_b64 = _b64e(nonce)
        msg = _challenge_message(nonce_b64, our_onion)
        sig = crypto_utils.sign_post(msg, ed25519_private_b64)
        logger.debug(f"Built challenge response for {peer_onion}")
        return sig

    def has_pending_challenge(self, onion_address: str) -> bool:
        """True if we have a challenge from this peer waiting to be signed."""
        with self._lock:
            return onion_address in self._received
