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
SecretFire — anonymous P2P microblogging over Tor
Entry point: starts Tor, initialises the node, launches the Flask server,
and opens the browser.
"""

import json
import sys
import time
import logging
import threading
import webbrowser
import base64
import os
import socket
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("main")

import storage
import crypto_utils
from tor_manager import TorManager
from tor_updater import check_and_update, start_background_updater
from gossip import GossipManager
from api_server import create_app
from config import (
    FLASK_HOST, FLASK_PORT, KEY_FILE, DATA_DIR,
    SEED_NODES
)


def load_or_create_identity() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if KEY_FILE.exists():
        try:
            with open(KEY_FILE) as f:
                identity = json.load(f)
            logger.info(f"Loaded node identity: {identity.get('node_id')}")
            return identity
        except Exception:
            logger.warning("Corrupted key file, generating new identity")

    identity = crypto_utils.generate_node_identity()
    with open(KEY_FILE, "w") as f:
        json.dump(identity, f, indent=2)
    logger.info(f"Generated new node identity: {identity['node_id']}")
    return identity


def load_or_create_broadcast_key(identity: dict) -> bytes:
    key_data = storage.get_key("broadcast_key")
    if key_data:
        return base64.b64decode(key_data)
    key = crypto_utils.generate_broadcast_key()
    storage.save_key("broadcast_key", "aes256", base64.b64encode(key).decode())
    return key


def bootstrap_seed_nodes():
    for addr in SEED_NODES:
        storage.save_peer(addr)


def wait_for_server(port: int, timeout: float = 15.0) -> bool:
    """Block until the Flask server is accepting connections or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def start_server(app) -> threading.Thread:
    """Start the Flask/Waitress server in a background daemon thread."""
    def _run():
        try:
            from waitress import serve
            serve(app, host=FLASK_HOST, port=FLASK_PORT)
        except ImportError:
            app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)

    t = threading.Thread(target=_run, daemon=True, name="flask-server")
    t.start()
    return t


def open_window(port: int):
    """
    Open the UI in a standalone native window via pywebview.
    Falls back to the system browser if pywebview is unavailable
    (e.g. missing system WebKit on some Linux installs).
    """
    url = f"http://127.0.0.1:{port}"
    try:
        import webview
        logger.info("Opening SecretFire window…")
        window = webview.create_window(
            "SecretFire",
            url,
            width=1200,
            height=800,
            min_size=(800, 600),
            resizable=True,
        )
        webview.start()
    except Exception as exc:
        logger.warning(f"pywebview unavailable ({exc}) — falling back to browser.")
        webbrowser.open(url)
        # Keep the process alive — Flask runs in a daemon thread so the
        # whole process would exit the moment main() returns otherwise.
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


def main():
    print(r"""
                             __  _______
   ________  _____________  / /_/ ____(_)_______
  / ___/ _ \/ ___/ ___/ _ \/ __/ /_  / / ___/ _ \
 (__  )  __/ /__/ /  /  __/ /_/ __/ / / /  /  __/
/____/\___/\___/_/   \___/\__/_/   /_/_/   \___/

  Anonymous P2P Microblogging  v0.1.5  (YOU SHALL NOT PASS!!! )
    """)

    logger.info("Initialising storage...")
    storage.init_db()

    logger.info("Loading node identity...")
    identity = load_or_create_identity()
    broadcast_key = load_or_create_broadcast_key(identity)

    logger.info("Bootstrapping seed nodes...")
    bootstrap_seed_nodes()

    logger.info("Checking Tor binary…")
    check_and_update()

    logger.info("Starting Tor...")
    tor = TorManager()
    tor.start()
    start_background_updater()

    if tor.demo_mode:
        logger.warning("Running in DEMO MODE — messages are NOT anonymous")
    else:
        logger.info(f"Hidden service: {tor.onion_address}")

    gossip = GossipManager(tor, identity, broadcast_key)
    gossip.start()

    app = create_app(tor, gossip, identity)

    logger.info(f"SecretFire running at http://127.0.0.1:{FLASK_PORT}")
    start_server(app)

    if not wait_for_server(FLASK_PORT):
        logger.warning("Server did not become ready in time — opening anyway.")

    open_window(FLASK_PORT)


if __name__ == "__main__":
    main()
