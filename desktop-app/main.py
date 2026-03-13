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
GhostWire — anonymous P2P microblogging over Tor
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


def open_browser(port: int):
    time.sleep(2.5)
    url = f"http://127.0.0.1:{port}"
    logger.info(f"Opening browser: {url}")
    webbrowser.open(url)


def main():
    print(r"""
   _____ _               _  __      ___ _
  / ____| |             | | \ \    / (_) |
 | |  __| |__   ___  ___| |_ \ \  / / _| |_ ___
 | | |_ | '_ \ / _ \/ __| __| \ \/ / | | __/ _ \
 | |__| | | | | (_) \__ \ |_   \  /  | | ||  __/
  \_____|_| |_|\___/|___/\__|   \/   |_|\__\___|

  Anonymous P2P Microblogging  v0.1.0
    """)

    logger.info("Initialising storage...")
    storage.init_db()

    logger.info("Loading node identity...")
    identity = load_or_create_identity()
    broadcast_key = load_or_create_broadcast_key(identity)

    logger.info("Bootstrapping seed nodes...")
    bootstrap_seed_nodes()

    logger.info("Starting Tor...")
    tor = TorManager()
    tor.start()

    if tor.demo_mode:
        logger.warning("Running in DEMO MODE — messages are NOT anonymous")
    else:
        logger.info(f"Hidden service: {tor.onion_address}")

    gossip = GossipManager(tor, identity, broadcast_key)
    gossip.start()

    app = create_app(tor, gossip, identity)

    browser_thread = threading.Thread(target=open_browser, args=(FLASK_PORT,), daemon=True)
    browser_thread.start()

    logger.info(f"GhostWire running at http://127.0.0.1:{FLASK_PORT}")
    try:
        from waitress import serve
        serve(app, host=FLASK_HOST, port=FLASK_PORT)
    except ImportError:
        app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
