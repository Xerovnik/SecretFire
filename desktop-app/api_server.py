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

import json
import re
import uuid
import time
import logging
import os
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS
import storage
import crypto_utils
import log_buffer
from config import KEY_FILE, APP_VERSION

logger = logging.getLogger("api_server")

WEB_DIR = Path(__file__).parent / "web"


def _save_file_dialog(default_name: str, content: str) -> str | None:
    """
    Open a native OS save-file dialog and write `content` to the chosen path.
    Returns the saved path, or None if the user cancelled.
    Works on Windows, Linux (X11), and macOS.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.asksaveasfilename(
            parent=root,
            title="Export SecretFire Identity",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON backup", "*.json"), ("All files", "*.*")],
        )
        root.destroy()
        if not path:
            return None
        Path(path).write_text(content, encoding="utf-8")
        return path
    except Exception as e:
        logger.error(f"Save dialog failed: {e}")
        # Fallback: save to Downloads folder
        import os
        downloads = Path(os.path.expanduser("~/Downloads"))
        downloads.mkdir(parents=True, exist_ok=True)
        fallback = downloads / default_name
        fallback.write_text(content, encoding="utf-8")
        return str(fallback)


def create_app(tor_manager, gossip_manager, node_identity: dict) -> Flask:
    app = Flask(__name__, static_folder=str(WEB_DIR))
    CORS(app)

    @app.route("/")
    def index():
        return send_file(str(WEB_DIR / "index.html"))

    @app.route("/<path:filename>")
    def static_files(filename):
        return send_from_directory(str(WEB_DIR), filename)

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #

    @app.route("/api/status")
    def status():
        tor_status = tor_manager.status()
        # Normalise: older tor_manager returns "running" not "connected"
        if "connected" not in tor_status:
            tor_status["connected"] = tor_status.get("running", False)
        stats = storage.get_stats()
        return jsonify({
            "app": "SecretFire",
            "version": APP_VERSION,
            "tor": tor_status,
            "node_id": node_identity.get("node_id", "unknown"),
            "public_key": node_identity.get("ed25519_public", ""),
            "stats": stats,
        })

    # ------------------------------------------------------------------ #
    # Posts
    # ------------------------------------------------------------------ #

    @app.route("/api/posts", methods=["GET"])
    def get_posts():
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = int(request.args.get("offset", 0))
        root_only = request.args.get("root_only", "0") == "1"
        posts = storage.get_posts(limit=limit, offset=offset, root_only=root_only)

        post_ids = [p["id"] for p in posts]
        reply_counts = storage.get_reply_counts(post_ids)
        nicknames = storage.get_nicknames()

        for p in posts:
            p["reply_count"] = reply_counts.get(p["id"], 0)
            p["author_nickname"] = nicknames.get(p.get("author_pubkey", ""), None)

        return jsonify({"posts": posts, "count": len(posts)})

    @app.route("/api/posts/<post_id>/replies", methods=["GET"])
    def get_replies(post_id):
        replies = storage.get_replies(post_id)
        nicknames = storage.get_nicknames()
        for r in replies:
            r["author_nickname"] = nicknames.get(r.get("author_pubkey", ""), None)
        return jsonify({"replies": replies, "count": len(replies)})

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

        parent_id = data.get("parent_id") or None

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
            parent_id=parent_id,
        )

        if not ok:
            return jsonify({"error": "Failed to save post"}), 500

        post_envelope = {
            "post_id": post_id,
            "content": content,
            "author_pubkey": node_identity["ed25519_public"],
            "signature": signature,
            "timestamp": ts,
            "parent_id": parent_id,
        }

        try:
            gossip_manager.broadcast_post(post_envelope)
        except Exception as e:
            logger.warning(f"Broadcast failed (post saved locally): {e}")

        return jsonify({"success": True, "post_id": post_id, "timestamp": ts}), 201

    # ------------------------------------------------------------------ #
    # Peers
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    # Nicknames
    # ------------------------------------------------------------------ #

    @app.route("/api/nicknames", methods=["GET"])
    def get_nicknames():
        return jsonify({"nicknames": storage.get_nicknames()})

    @app.route("/api/nicknames/<pubkey>", methods=["PUT"])
    def set_nickname(pubkey):
        data = request.get_json()
        if not data or "nickname" not in data:
            return jsonify({"error": "nickname required"}), 400
        nick = data["nickname"].strip()
        if not nick:
            storage.delete_nickname(pubkey)
            return jsonify({"success": True, "action": "deleted"})
        if len(nick) > 32:
            return jsonify({"error": "nickname too long (max 32 chars)"}), 400
        storage.set_nickname(pubkey, nick)
        return jsonify({"success": True, "nickname": nick})

    @app.route("/api/nicknames/<pubkey>", methods=["DELETE"])
    def delete_nickname(pubkey):
        storage.delete_nickname(pubkey)
        return jsonify({"success": True})

    # ------------------------------------------------------------------ #
    # Identity backup / restore
    # ------------------------------------------------------------------ #

    @app.route("/api/identity/export", methods=["GET"])
    def export_identity():
        if not KEY_FILE.exists():
            return jsonify({"error": "No identity found"}), 404
        try:
            identity = json.loads(KEY_FILE.read_text())
            backup = {
                "secretfire_identity_backup": True,
                "backup_version": "1",
                "node_id": identity.get("node_id"),
                "ed25519_public": identity.get("ed25519_public"),
                "ed25519_private": identity.get("ed25519_private"),
            }
            return jsonify(backup)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/identity/export-file", methods=["POST"])
    def export_identity_to_file():
        """Open a native OS save-file dialog and write the identity JSON there."""
        if not KEY_FILE.exists():
            return jsonify({"error": "No identity found"}), 404
        try:
            identity = json.loads(KEY_FILE.read_text())
            backup = {
                "secretfire_identity_backup": True,
                "backup_version": "1",
                "node_id": identity.get("node_id"),
                "ed25519_public": identity.get("ed25519_public"),
                "ed25519_private": identity.get("ed25519_private"),
            }
            content = json.dumps(backup, indent=2)
            raw_id = (identity.get('node_id') or '')
            safe_id = re.sub(r'[^a-zA-Z0-9_-]', '', raw_id)[:8]
            default_name = f"secretfire-identity-{safe_id}.json"

            saved_path = _save_file_dialog(default_name, content)
            if saved_path is None:
                return jsonify({"cancelled": True})
            return jsonify({"success": True, "path": saved_path})
        except Exception as e:
            logger.error(f"Identity export failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/identity/import", methods=["POST"])
    def import_identity():
        data = request.get_json()
        if not data or not data.get("secretfire_identity_backup"):
            return jsonify({"error": "Invalid backup file format"}), 400
        required = {"node_id", "ed25519_public", "ed25519_private"}
        if not required.issubset(data.keys()):
            return jsonify({"error": "Backup is missing required fields"}), 400
        try:
            identity = {
                "node_id": data["node_id"],
                "ed25519_public": data["ed25519_public"],
                "ed25519_private": data["ed25519_private"],
            }
            KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
            KEY_FILE.write_text(json.dumps(identity, indent=2))
            return jsonify({
                "success": True,
                "node_id": identity["node_id"],
                "message": "Identity imported. Restart SecretFire to apply."
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ------------------------------------------------------------------ #
    # Log console
    # ------------------------------------------------------------------ #

    @app.route("/api/logs")
    def get_logs():
        since = float(request.args.get("since", 0))
        limit = min(int(request.args.get("limit", 200)), 500)
        lines = log_buffer.get_lines(since_ts=since, limit=limit)
        return jsonify({"lines": lines})

    # ------------------------------------------------------------------ #
    # Sync
    # ------------------------------------------------------------------ #

    @app.route("/api/sync-now", methods=["POST"])
    def sync_now():
        try:
            gossip_manager._sync_all_peers(include_inactive=True)
            gossip_manager._process_complete_fragments()
            return jsonify({"success": True, "stats": storage.get_stats()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ------------------------------------------------------------------ #
    # Auto-update
    # ------------------------------------------------------------------ #

    _update_cache: dict = {"checked": False, "result": None}
    _download_state: dict = {"status": "idle", "progress": 0, "error": None, "path": None}

    @app.route("/api/update/check", methods=["GET"])
    def update_check():
        import updater as _updater
        force = request.args.get("force") == "1"
        if not _update_cache["checked"] or force:
            result = _updater.check_for_update()
            _update_cache["result"] = result
            _update_cache["checked"] = True
        r = _update_cache["result"]
        if r is None:
            return jsonify({"update_available": False, "error": "check failed",
                            "current": node_identity.get("version", "unknown")})
        return jsonify(r)

    @app.route("/api/update/download", methods=["POST"])
    def update_download():
        import updater as _updater
        import threading as _threading
        if _download_state["status"] == "downloading":
            return jsonify({"error": "Already downloading"}), 409
        info = _update_cache.get("result") or {}
        url = info.get("download_url")
        if not url:
            return jsonify({"error": "No download URL — check for updates first"}), 400

        def _run():
            _download_state.update({"status": "downloading", "progress": 0,
                                    "error": None, "path": None})
            try:
                def _prog(pct):
                    _download_state["progress"] = pct
                path = _updater.download_update(url, progress_cb=_prog)
                _download_state.update({"status": "ready", "progress": 100, "path": path})
            except Exception as e:
                logger.error(f"Update download failed: {e}")
                _download_state.update({"status": "error", "error": str(e)})

        _threading.Thread(target=_run, daemon=True).start()
        return jsonify({"started": True})

    @app.route("/api/update/progress", methods=["GET"])
    def update_progress():
        return jsonify(_download_state)

    @app.route("/api/update/apply", methods=["POST"])
    def update_apply():
        if _download_state["status"] != "ready":
            return jsonify({"error": "No update staged — download first"}), 400
        staged = _download_state.get("path")
        if not staged:
            return jsonify({"error": "Staged path missing"}), 400
        import threading as _threading
        import updater as _updater

        def _do_apply():
            import time
            try:
                _updater.apply_update(staged)
            except Exception as e:
                logger.error(f"apply_update failed: {e}")
            time.sleep(0.3)
            try:
                logger.info("Stopping Tor before update restart…")
                tor_manager.stop()
            except Exception as e:
                logger.warning(f"Tor stop error during update: {e}")
            os._exit(0)

        _threading.Thread(target=_do_apply, daemon=True).start()
        return jsonify({"exiting": True})

    # ------------------------------------------------------------------ #
    # Peer-to-peer endpoints
    # ------------------------------------------------------------------ #

    @app.route("/fragment", methods=["POST"])
    def receive_fragment():
        if request.content_length and request.content_length > 16_384:
            return jsonify({"error": "payload too large"}), 413
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
