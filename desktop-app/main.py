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
and opens the browser/webview.
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

# Set up the stdout handler FIRST so basicConfig installs it before log_buffer
# adds its own handler (basicConfig is a no-op if handlers already exist).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("main")

# Install log buffer AFTER basicConfig — adds as a second handler so both
# stdout and the in-app Console tab receive every log record.
# Also wraps sys.stdout so print() calls appear in the Console tab.
import log_buffer
log_buffer.install()

import storage
import crypto_utils
from tor_manager import TorManager
from tor_updater import check_and_update, start_background_updater
from gossip import GossipManager
from api_server import create_app
from config import (
    FLASK_HOST, FLASK_PORT, KEY_FILE, DATA_DIR,
    SEED_NODES, APP_VERSION
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
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _hide_console_window():
    """
    On Windows, hide the separate console window if one is present.
    Works whether running from source or a console=True PyInstaller binary.
    No-op on macOS/Linux and when there is no console window to hide.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE = 0
    except Exception:
        pass


def start_server(app) -> threading.Thread:
    # Suppress the noisy but harmless waitress task-queue depth warning
    logging.getLogger("waitress.queue").setLevel(logging.ERROR)

    def _run():
        try:
            from waitress import serve
            serve(app, host=FLASK_HOST, port=FLASK_PORT)
        except ImportError:
            app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)

    t = threading.Thread(target=_run, daemon=True, name="flask-server")
    t.start()
    return t


def _make_tray_image():
    """Create a simple system tray icon using PIL."""
    try:
        from PIL import Image, ImageDraw
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # Cyan circle background
        d.ellipse([2, 2, size - 2, size - 2], fill=(0, 200, 220, 255))
        # Dark inner circle
        d.ellipse([10, 10, size - 10, size - 10], fill=(8, 14, 26, 255))
        # Cyan flame-like dots (simplified)
        d.ellipse([24, 22, 40, 38], fill=(0, 229, 255, 255))
        d.ellipse([20, 32, 44, 52], fill=(0, 180, 200, 200))
        return img
    except Exception:
        return None


def start_tray(app_url: str, tor_manager=None):
    """Start the system tray icon in a background thread."""
    try:
        import pystray
        img = _make_tray_image()
        if not img:
            logger.warning("System tray: PIL not available — skipping tray icon")
            return

        def open_app(icon, item):
            webbrowser.open(app_url)

        def quit_app(icon, item):
            icon.stop()
            if tor_manager is not None:
                logger.info("Stopping Tor before exit…")
                try:
                    tor_manager.stop()
                except Exception as e:
                    logger.warning(f"Tor stop error: {e}")
            os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem("Open SecretFire", open_app, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", quit_app),
        )

        icon = pystray.Icon("SecretFire", img, "SecretFire", menu)

        t = threading.Thread(target=icon.run, daemon=True, name="tray")
        t.start()
        logger.info("System tray icon started (right-click to quit)")
    except ImportError:
        logger.warning("pystray not installed — system tray not available")
    except Exception as e:
        logger.warning(f"System tray failed to start: {e}")


def open_window(port: int):
    url = f"http://127.0.0.1:{port}"
    try:
        import webview
        logger.info("Opening SecretFire window…")
        window = webview.create_window(
            "SecretFire",
            url,
            width=1300,
            height=860,
            min_size=(900, 650),
            resizable=True,
        )
        webview.start()
        # After webview window closes, process stays alive via tray
        logger.info("Window closed — app running in system tray")
        while True:
            time.sleep(5)
    except Exception as exc:
        logger.warning(f"pywebview unavailable ({exc}) — falling back to browser.")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


def main():
    print(r"""
  ____                    _   _____ _
 / ___|  ___  ___ _ __ __|_||  ___(_)_ __ ___
 \___ \ / _ \/ __| '__/ _ \ || |_  | | '__/ _ \
  ___) |  __/ (__| | |  __/ ||  _| | | | |  __/
 |____/ \___|\___|_|  \___|_||_|   |_|_|  \___|
""")
    print(f"  Anonymous P2P Microblogging  v{APP_VERSION}\n")

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
    elif tor.using_bridges:
        logger.info(f"Tor connected via obfs4 bridges | hidden service: {tor.onion_address}")
    else:
        logger.info(f"Tor connected | hidden service: {tor.onion_address}")

    gossip = GossipManager(tor, identity, broadcast_key)
    gossip.start()

    app = create_app(tor, gossip, identity)

    logger.info(f"SecretFire running at http://127.0.0.1:{FLASK_PORT}")
    start_server(app)

    if not wait_for_server(FLASK_PORT):
        logger.warning("Server did not become ready in time — opening anyway.")

    url = f"http://127.0.0.1:{FLASK_PORT}"
    start_tray(url, tor)
    _hide_console_window()
    open_window(FLASK_PORT)


if __name__ == "__main__":
    main()
