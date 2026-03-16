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
Flask API server — serves the local web UI and exposes API endpoints.
Also exposes /fragment and /api/sync for peer-to-peer communication.
"""

import uuid
import time
import logging
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS
import storage
import crypto_utils

logger = logging.getLogger("api_server")

WEB_DIR = Path(__file__).parent / "web"


def create_app(tor_manager, gossip_manager, node_identity: dict) -> Flask:
    app = Flask(__name__, static_folder=str(WEB_DIR))
    CORS(app)

    @app.route("/")
    def index():
        return send_file(str(WEB_DIR / "index.html"))

    @app.route("/<path:filename>")
    def static_files(filename):
        return send_from_directory(str(WEB_DIR), filename)

    @app.route("/api/status")
    def status():
        tor_status = tor_manager.status()
        stats = storage.get_stats()
        return jsonify({
            "app": "SecretFire",
            "version": "0.1.0",
            "tor": tor_status,
            "node_id": node_identity.get("node_id", "unknown"),
            "public_key": node_identity.get("ed25519_public", ""),
            "stats": stats,
        })

    @app.route("/api/posts", methods=["GET"])
    def get_posts():
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = int(request.args.get("offset", 0))
        posts = storage.get_posts(limit=limit, offset=offset)
        return jsonify({"posts": posts, "count": len(posts)})

    @app.route("/api/posts", methods=["POST"])
    def create_post():
        data = request.get_json()
        if not data or "content" not in data:
            return jsonify({"error": "content required"}), 400

        content = data["content"].strip()
        if not content:
            return jsonify({"error": "content cannot be empty"}), 400
        if len(content) > 500:
            return jsonify({"error": "Post too long (max 500 chars)"}), 400

        post_id = str(uuid.uuid4())
        ts = int(time.time())

        signature = crypto_utils.sign_post(
            content + post_id,
            node_identity["ed25519_private"]
        )

        ok = storage.save_post(
            post_id=post_id,
            content=content,
            author_pubkey=node_identity["ed25519_public"],
            signature=signature,
            timestamp=ts,
            source_peer="local",
        )

        if not ok:
            return jsonify({"error": "Failed to save post"}), 500

        post_envelope = {
            "post_id": post_id,
            "content": content,
            "author_pubkey": node_identity["ed25519_public"],
            "signature": signature,
            "timestamp": ts,
        }

        try:
            gossip_manager.broadcast_post(post_envelope)
        except Exception as e:
            logger.warning(f"Broadcast failed (post saved locally): {e}")

        return jsonify({"success": True, "post_id": post_id, "timestamp": ts}), 201

    @app.route("/api/peers", methods=["GET"])
    def get_peers():
        peers = storage.get_peers()
        return jsonify({"peers": peers})

    @app.route("/api/peers", methods=["POST"])
    def add_peer():
        data = request.get_json()
        if not data or "onion_address" not in data:
            return jsonify({"error": "onion_address required"}), 400
        addr = data["onion_address"].strip()
        if not addr:
            return jsonify({"error": "invalid address"}), 400
        storage.save_peer(addr)
        return jsonify({"success": True, "onion_address": addr})

    @app.route("/api/peers/<path:onion_address>", methods=["DELETE"])
    def remove_peer(onion_address):
        storage.update_peer_status(onion_address, False)
        return jsonify({"success": True})

    @app.route("/api/sync-now", methods=["POST"])
    def sync_now():
        try:
            # Always try all peers on manual sync, not just active ones
            gossip_manager._sync_all_peers(include_inactive=True)
            gossip_manager._process_complete_fragments()
            return jsonify({"success": True, "stats": storage.get_stats()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/fragment", methods=["POST"])
    def receive_fragment():
        data = request.get_json()
        if not data or "fragment" not in data:
            return jsonify({"error": "fragment required"}), 400
        ok = gossip_manager.receive_fragment(
            data["fragment"],
            data.get("broadcast_key")
        )
        return jsonify({"success": ok})

    @app.route("/api/sync", methods=["POST"])
    def sync_handler():
        data = request.get_json() or {}
        result = gossip_manager.handle_sync_request(data)
        return jsonify(result)

    return app
