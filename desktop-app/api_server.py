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
import socket
import datetime
import logging
import os
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS
import storage
import crypto_utils
import log_buffer
from config import APP_VERSION

logger = logging.getLogger("api_server")

WEB_DIR = Path(__file__).parent / "web"


def _save_file_dialog(default_name: str, content: str) -> str | None:
    """
    Open a native OS save-file dialog and write `content` to the chosen path.
    Returns the saved path, or None if the user cancelled.
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
        downloads = Path(os.path.expanduser("~/Downloads"))
        downloads.mkdir(parents=True, exist_ok=True)
        fallback = downloads / default_name
        fallback.write_text(content, encoding="utf-8")
        return str(fallback)


def _prompt_import_password(title: str, message: str, confirm: bool = True) -> str | None:
    """Show a branded SecretFire password dialog for import re-encryption. Returns password or None."""
    try:
        import tkinter as tk
        from tkinter import messagebox, font as tkfont

        BG      = "#080e1a"
        BG2     = "#0d1828"
        CYAN    = "#00e5ff"
        FG      = "#c8d6e5"
        FG_DIM  = "#3d5470"
        SEP     = "#112238"

        result = [None]
        root = tk.Tk()
        root.withdraw()
        dlg = tk.Toplevel(root)
        dlg.title("SecretFire")
        dlg.resizable(False, False)
        dlg.configure(bg=BG)
        try:
            dlg.grab_set()
        except Exception:
            pass
        dlg.attributes("-topmost", True)

        def _font(*names, size=10, weight="normal"):
            for name in names:
                try:
                    f = tkfont.Font(family=name, size=size, weight=weight)
                    if f.actual("family").lower().replace(" ", "") == name.lower().replace(" ", ""):
                        return f
                except Exception:
                    pass
            return tkfont.Font(size=size, weight=weight)

        f_title = _font("Chakra Petch", "Rajdhani", "Segoe UI", "Arial", size=18, weight="bold")
        f_tag   = _font("Rajdhani", "Segoe UI", "Arial", size=9)
        f_label = _font("Rajdhani", "Segoe UI", "Arial", size=10, weight="bold")
        f_body  = _font("Segoe UI", "Arial", size=10)
        f_entry = _font("Consolas", "Courier New", "Menlo", "Monospace", size=11)
        f_btn   = _font("Rajdhani", "Segoe UI", "Arial", size=10, weight="bold")

        outer = tk.Frame(dlg, bg=BG, padx=32, pady=24)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="SecretFire", font=f_title, fg=CYAN, bg=BG).pack(anchor="w")
        tk.Label(outer, text="anonymous  ·  encrypted  ·  decentralized",
                 font=f_tag, fg=FG_DIM, bg=BG).pack(anchor="w", pady=(2, 0))
        tk.Frame(outer, bg=SEP, height=1).pack(fill="x", pady=(12, 16))
        tk.Label(outer, text=message, font=f_body, fg=FG, bg=BG,
                 wraplength=380, justify="left").pack(anchor="w", pady=(0, 18))

        def _entry_block(label_text: str) -> tk.Entry:
            tk.Label(outer, text=label_text, font=f_label,
                     fg=CYAN, bg=BG).pack(anchor="w", pady=(0, 4))
            border = tk.Frame(outer, bg=CYAN, padx=1, pady=1)
            border.pack(fill="x", pady=(0, 14))
            e = tk.Entry(border, show="•", font=f_entry,
                         bg=BG2, fg=FG, insertbackground=CYAN,
                         relief="flat", bd=0)
            e.pack(fill="x", ipady=7, padx=1)
            return e

        pw_entry = _entry_block("Password")
        pw_entry.focus_set()
        pw2_entry = None
        if confirm:
            pw2_entry = _entry_block("Confirm password")

        def on_ok(event=None):
            pw = pw_entry.get()
            if not pw:
                messagebox.showerror("SecretFire", "Password cannot be empty.", parent=dlg)
                return
            if confirm and pw2_entry and pw != pw2_entry.get():
                messagebox.showerror("SecretFire", "Passwords do not match.", parent=dlg)
                return
            result[0] = pw
            dlg.destroy()
            root.destroy()

        def on_cancel():
            dlg.destroy()
            root.destroy()

        btn_row = tk.Frame(outer, bg=BG)
        btn_row.pack(pady=(6, 0))
        btn_label = "SET PASSWORD" if confirm else "UNLOCK"
        tk.Button(btn_row, text=btn_label, font=f_btn,
                  fg=BG, bg=CYAN, activebackground="#00b8d4", activeforeground=BG,
                  relief="flat", bd=0, padx=20, pady=7, cursor="hand2",
                  command=on_ok).pack(side="left", padx=(0, 12))
        tk.Button(btn_row, text="Cancel", font=f_btn,
                  fg=FG_DIM, bg=BG, activebackground=BG2, activeforeground=FG,
                  relief="flat", bd=0, padx=12, pady=7, cursor="hand2",
                  command=on_cancel).pack(side="left")

        dlg.bind("<Return>", on_ok)
        dlg.bind("<Escape>", lambda e: on_cancel())
        dlg.update_idletasks()
        w = max(dlg.winfo_reqwidth(), 460)
        h = dlg.winfo_reqheight()
        x = (dlg.winfo_screenwidth()  - w) // 2
        y = (dlg.winfo_screenheight() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")
        root.mainloop()
        return result[0]
    except Exception as e:
        logger.error(f"Import password dialog failed: {e}")
        return None


def create_app(
    tor_manager,
    gossip_manager,
    node_identity: dict,
    identity_manager=None,
) -> Flask:
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
        if "connected" not in tor_status:
            tor_status["connected"] = tor_status.get("running", False)
        stats = storage.get_stats()
        return jsonify({
            "app":        "SecretFire",
            "version":    APP_VERSION,
            "tor":        tor_status,
            "node_id":    node_identity.get("node_id", "unknown"),
            "public_key": node_identity.get("ed25519_public", ""),
            "stats":      stats,
        })

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #

    @app.route("/api/diagnostics")
    def diagnostics():
        from config import TOR_DATA_DIR, TOR_HIDDEN_SERVICE_DIR, DB_PATH
        checks = []

        def chk(key, label, ok, note="", warn=False):
            checks.append({"key": key, "label": label, "ok": ok, "warn": warn, "note": note})

        # 1. Tor process running
        ts = tor_manager.status()
        chk("tor_running", "Tor process running",
            ts.get("running", False),
            "Check the Console tab for startup errors." if not ts.get("running") else "")

        # 2. Bootstrap: tor_manager.is_running is set True only after 100% bootstrap.
        #    Tor logs to stdout only (no tor.log on disk), so is_running is the
        #    only reliable in-process indicator of completed bootstrap.
        bootstrapped = ts.get("running", False)
        chk("bootstrap", "Tor bootstrapped (100%)" if bootstrapped else "Tor not yet bootstrapped",
            bootstrapped,
            "" if bootstrapped else
            "Tor is still connecting. Wait 30–90 s and run diagnostics again. "
            "If stuck after 2 minutes, try a different network or enable bridges.")

        # 3. Hidden service hostname
        hostname_file = TOR_HIDDEN_SERVICE_DIR / "hostname"
        onion = ""
        try:
            if hostname_file.exists():
                onion = hostname_file.read_text().strip()
        except Exception:
            pass
        chk("hidden_service", "Hidden service address generated",
            bool(onion),
            onion if onion else "Hostname file missing. Tor may not have finished publishing.")

        # 4. SOCKS port listening
        socks_port = ts.get("socks_port") or 9150
        socks_ok = False
        try:
            with socket.create_connection(("127.0.0.1", socks_port), timeout=2):
                socks_ok = True
        except OSError:
            pass
        chk("socks_port", f"SOCKS proxy listening (:{socks_port})",
            socks_ok,
            "" if socks_ok else "SOCKS port not open. Tor may have failed to start.")

        # 5. Self-reachability via onion (only attempt if prerequisites pass)
        self_ok   = False
        self_warn = False
        self_note = ""
        if socks_ok and onion and bootstrapped:
            try:
                import requests as _req
                proxies = {
                    "http":  f"socks5h://127.0.0.1:{socks_port}",
                    "https": f"socks5h://127.0.0.1:{socks_port}",
                }
                # The hidden service exposes port 80 and forwards internally to Flask.
                # Do NOT use FLASK_PORT (7474) here — that is only the local bind port.
                r = _req.get(
                    f"http://{onion}/api/status",
                    proxies=proxies, timeout=30
                )
                self_ok   = r.status_code == 200
                self_note = ("Your node is reachable from within the Tor network."
                             if self_ok else f"Got HTTP {r.status_code} — hidden service is up but returned an error.")
            except Exception as e:
                err = str(e).lower()
                if "timed out" in err or "time out" in err or "timeout" in err:
                    # Timeout = descriptor still propagating; not a hard failure
                    self_warn = True
                    self_note = ("Circuit timed out — the hidden service descriptor is still propagating. "
                                 "This is normal for the first 2–5 minutes after startup. "
                                 "Wait a little longer and run diagnostics again.")
                elif "refused" in err or "connect" in err:
                    self_note = ("Connection refused — the hidden service port may not be reachable. "
                                 "Check the Console tab for errors.")
                else:
                    self_note = str(e)
        else:
            self_note = "Skipped — requires Tor running, SOCKS open, and 100% bootstrap."
        chk("self_reach", "Self-onion reachability", self_ok, self_note, warn=self_warn)

        # 6. Clearnet blocked (intentional — OnionTrafficOnly)
        clearnet_blocked = False
        if socks_ok:
            try:
                with socket.create_connection(("127.0.0.1", socks_port), timeout=2) as s:
                    s.sendall(b"\x05\x01\x00")
                    s.recv(2)
                    # try CONNECT to a clearnet IP — should be refused
                    s.sendall(b"\x05\x01\x00\x01\x01\x01\x01\x01\x00\x50")
                    resp = s.recv(10)
                    clearnet_blocked = len(resp) >= 2 and resp[1] != 0x00
            except Exception:
                clearnet_blocked = True
        chk("clearnet_blocked", "Clearnet traffic blocked (OnionTrafficOnly)",
            clearnet_blocked,
            "Expected — this is a security feature. The SOCKS proxy only allows .onion traffic." if clearnet_blocked
            else "Clearnet appears reachable through SOCKS. OnionTrafficOnly may not be active.")

        # 7. System clock (report UTC so user can compare)
        utc_now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        chk("clock", f"System clock ({utc_now})",
            True,
            "Tor requires accurate time (within ~30 s). If peers can't connect, verify your clock is correct.")

        # 8. Database reachable
        db_ok = False
        db_note = ""
        try:
            stats = storage.get_stats()
            posts = stats.get("posts", 0)
            peers = stats.get("peers", 0)
            db_ok = True
            db_note = f"{posts} post(s), {peers} peer(s) in local database."
        except Exception as e:
            db_note = str(e)
        chk("database", "Local database accessible", db_ok, db_note)

        # 9. Peer count detail
        try:
            peer_rows = storage.get_peers()
            verified = sum(1 for p in peer_rows if p.get("auth_verified"))
            unverified = len(peer_rows) - verified
            chk("peers", f"Known peers ({len(peer_rows)} total)",
                len(peer_rows) > 0,
                f"{verified} verified, {unverified} unverified. Add peers via the Peers tab." if len(peer_rows) == 0
                else f"{verified} verified, {unverified} unverified.")
        except Exception:
            chk("peers", "Known peers", False, "Could not query peer table.")

        return jsonify({
            "checks": checks,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "version": APP_VERSION,
        })

    # ------------------------------------------------------------------ #
    # Posts
    # ------------------------------------------------------------------ #

    @app.route("/api/posts", methods=["GET"])
    def get_posts():
        limit     = min(int(request.args.get("limit", 50)), 200)
        offset    = int(request.args.get("offset", 0))
        root_only = request.args.get("root_only", "0") == "1"
        posts     = storage.get_posts(limit=limit, offset=offset, root_only=root_only)

        post_ids     = [p["id"] for p in posts]
        reply_counts = storage.get_reply_counts(post_ids)
        nicknames    = storage.get_nicknames()

        for p in posts:
            p["reply_count"]    = reply_counts.get(p["id"], 0)
            p["author_nickname"] = nicknames.get(p.get("author_pubkey", ""), None)

        return jsonify({"posts": posts, "count": len(posts)})

    @app.route("/api/posts/<post_id>/replies", methods=["GET"])
    def get_replies(post_id):
        replies   = storage.get_replies(post_id)
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
        post_id   = str(uuid.uuid4())
        ts        = int(time.time())

        signature = crypto_utils.sign_post(
            content + post_id,
            node_identity["ed25519_private"],
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
            "post_id":      post_id,
            "content":      content,
            "author_pubkey": node_identity["ed25519_public"],
            "signature":    signature,
            "timestamp":    ts,
            "parent_id":    parent_id,
        }

        try:
            gossip_manager.broadcast_post(post_envelope)
        except Exception as e:
            logger.warning(f"Broadcast failed (post saved locally): {e}")

        return jsonify({"success": True, "post_id": post_id, "timestamp": ts}), 201

    @app.route("/api/posts/<post_id>", methods=["DELETE"])
    def delete_post(post_id):
        our_pubkey  = node_identity.get("ed25519_public", "")
        our_privkey = node_identity.get("ed25519_private", "")

        # Verify the requesting node is the author of this post
        author = storage.get_post_author_pubkey(post_id)
        if author and author != our_pubkey:
            return jsonify({"error": "You are not the author of this post"}), 403

        delete_ts  = int(time.time())
        canonical  = f"DELETE:{post_id}:{delete_ts}"
        delete_sig = crypto_utils.sign_post(canonical, our_privkey)

        # Save tombstone (also deletes post + replies locally)
        storage.save_delete_tombstone(post_id, our_pubkey, delete_sig, delete_ts)

        # Propagate to all peers immediately — don't wait for the gossip cycle
        tombstone = {
            "post_id":          post_id,
            "author_pubkey":    our_pubkey,
            "delete_signature": delete_sig,
            "delete_timestamp": delete_ts,
        }
        try:
            gossip_manager.broadcast_delete_tombstone(tombstone)
        except Exception as e:
            logger.warning(f"Delete tombstone broadcast failed: {e}")

        logger.info(f"Post {post_id[:12]}… deleted and tombstone propagated")
        return jsonify({"success": True, "propagated": True})

    @app.route("/api/delete_tombstone", methods=["POST"])
    def receive_delete_tombstone():
        """Peer-to-peer endpoint — peers push delete tombstones here directly."""
        data = request.get_json(silent=True) or {}
        applied = gossip_manager._apply_delete_tombstone(data)
        return jsonify({"applied": applied})

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
        """Return the in-memory identity as a JSON backup (plaintext — warn user)."""
        try:
            backup = {
                "secretfire_identity_backup": True,
                "backup_version":  "2",
                "node_id":         node_identity.get("node_id"),
                "ed25519_public":  node_identity.get("ed25519_public"),
                "ed25519_private": node_identity.get("ed25519_private"),
            }
            return jsonify(backup)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/identity/export-file", methods=["POST"])
    def export_identity_to_file():
        """Open a native OS save dialog and write the identity JSON there."""
        try:
            backup = {
                "secretfire_identity_backup": True,
                "backup_version":  "2",
                "node_id":         node_identity.get("node_id"),
                "ed25519_public":  node_identity.get("ed25519_public"),
                "ed25519_private": node_identity.get("ed25519_private"),
            }
            content  = json.dumps(backup, indent=2)
            raw_id   = (node_identity.get("node_id") or "")
            safe_id  = re.sub(r"[^a-zA-Z0-9_-]", "", raw_id)[:8]
            default  = f"secretfire-identity-{safe_id}.json"

            saved_path = _save_file_dialog(default, content)
            if saved_path is None:
                return jsonify({"cancelled": True})
            return jsonify({"success": True, "path": saved_path})
        except Exception as e:
            logger.error(f"Identity export failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/identity/import", methods=["POST"])
    def import_identity():
        """
        Accept a plaintext identity JSON backup, prompt the user for a new
        password via a native dialog, encrypt it with IdentityManager, and
        save.  The app must be restarted to load the new identity.
        """
        data = request.get_json()
        if not data or not data.get("secretfire_identity_backup"):
            return jsonify({"error": "Invalid backup file format"}), 400
        required = {"node_id", "ed25519_public", "ed25519_private"}
        if not required.issubset(data.keys()):
            return jsonify({"error": "Backup is missing required fields"}), 400

        if identity_manager is None:
            return jsonify({"error": "Identity manager not available"}), 500

        try:
            pw = _prompt_import_password(
                "SecretFire — Set Password for Imported Identity",
                "Set a password to encrypt the imported identity.\n\n"
                "You will need this password every time you start SecretFire.",
                confirm=True,
            )
            if pw is None:
                return jsonify({"cancelled": True})

            new_identity = {
                "node_id":         data["node_id"],
                "ed25519_public":  data["ed25519_public"],
                "ed25519_private": data["ed25519_private"],
            }
            identity_manager.migrate_legacy(new_identity, pw)
            return jsonify({
                "success":  True,
                "node_id":  new_identity["node_id"],
                "message":  "Identity imported and encrypted. Restart SecretFire to apply.",
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

    _update_cache:   dict = {"checked": False, "result": None}
    _download_state: dict = {
        "status": "idle", "progress": 0, "error": None, "path": None
    }

    @app.route("/api/update/check", methods=["GET"])
    def update_check():
        try:
            import updater as _updater
        except Exception as e:
            logger.warning(f"updater module unavailable: {e}")
            return jsonify({
                "update_available": False,
                "error": "updater unavailable — download the latest binary manually from GitHub",
                "current": APP_VERSION,
            })
        force = request.args.get("force") == "1"
        if not _update_cache["checked"] or force:
            result = _updater.check_for_update()
            _update_cache["result"]  = result
            _update_cache["checked"] = True
        r = _update_cache["result"]
        if r is None:
            return jsonify({
                "update_available": False,
                "error":   "check failed",
                "current": APP_VERSION,
            })
        return jsonify(r)

    @app.route("/api/update/download", methods=["POST"])
    def update_download():
        try:
            import updater as _updater
        except Exception as e:
            logger.warning(f"updater module unavailable: {e}")
            return jsonify({"error": "updater unavailable"}), 503
        import threading as _threading
        if _download_state["status"] == "downloading":
            return jsonify({"error": "Already downloading"}), 409
        info = _update_cache.get("result") or {}
        url  = info.get("download_url")
        if not url:
            return jsonify({"error": "No download URL — check for updates first"}), 400

        def _run():
            _download_state.update({
                "status": "downloading", "progress": 0, "error": None, "path": None
            })
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
            broadcast_key_b64=data.get("broadcast_key"),
            key_id=data.get("key_id"),
        )
        return jsonify({"success": ok})

    @app.route("/api/sync", methods=["POST"])
    def sync_handler():
        data   = request.get_json() or {}
        result = gossip_manager.handle_sync_request(data)
        return jsonify(result)

    return app
