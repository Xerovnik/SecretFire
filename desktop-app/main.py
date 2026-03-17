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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("main")

import log_buffer
log_buffer.install()

import storage
import crypto_utils
from identity import IdentityManager
from tor_manager import TorManager
from tor_updater import check_and_update, start_background_updater
from gossip import GossipManager
from api_server import create_app
from config import (
    FLASK_HOST, FLASK_PORT, KEY_FILE, DATA_DIR,
    SEED_NODES, APP_VERSION,
)


# ---------------------------------------------------------------------------
# Password dialog (native tkinter)
# ---------------------------------------------------------------------------

def _prompt_password(
    title: str,
    message: str,
    confirm: bool = False,
) -> str | None:
    """
    Show a native password prompt using tkinter.
    Returns the entered password or None if the user cancelled.
    """
    import tkinter as tk
    from tkinter import messagebox

    result = [None]

    root = tk.Tk()
    root.withdraw()

    dlg = tk.Toplevel(root)
    dlg.title(title)
    dlg.resizable(False, False)
    try:
        dlg.grab_set()
    except Exception:
        pass
    dlg.attributes("-topmost", True)

    frame = tk.Frame(dlg, padx=24, pady=16)
    frame.pack(fill="both", expand=True)

    tk.Label(
        frame, text=message, wraplength=340, justify="left", pady=4
    ).pack(anchor="w")

    tk.Label(frame, text="Password:", pady=(10, 2)).pack(anchor="w")
    pw_entry = tk.Entry(frame, show="*", width=38)
    pw_entry.pack(fill="x")
    pw_entry.focus_set()

    pw2_entry = None
    if confirm:
        tk.Label(frame, text="Confirm password:", pady=(8, 2)).pack(anchor="w")
        pw2_entry = tk.Entry(frame, show="*", width=38)
        pw2_entry.pack(fill="x")

    def on_ok(event=None):
        pw = pw_entry.get()
        if not pw:
            messagebox.showerror("Error", "Password cannot be empty.", parent=dlg)
            return
        if confirm and pw2_entry:
            if pw != pw2_entry.get():
                messagebox.showerror("Error", "Passwords do not match.", parent=dlg)
                return
            if len(pw) < 8:
                if not messagebox.askyesno(
                    "Weak password",
                    "Password is shorter than 8 characters.\n\nUse it anyway?",
                    parent=dlg,
                ):
                    return
        result[0] = pw
        dlg.destroy()
        root.destroy()

    def on_cancel():
        dlg.destroy()
        root.destroy()

    btn_frame = tk.Frame(frame, pady=12)
    btn_frame.pack()
    tk.Button(btn_frame, text="OK",     command=on_ok,     width=10).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Cancel", command=on_cancel, width=10).pack(side="left", padx=5)

    dlg.bind("<Return>", on_ok)
    dlg.bind("<Escape>", lambda e: on_cancel())

    dlg.update_idletasks()
    w, h = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
    x = (dlg.winfo_screenwidth()  - w) // 2
    y = (dlg.winfo_screenheight() - h) // 2
    dlg.geometry(f"+{x}+{y}")

    root.mainloop()
    return result[0]


# ---------------------------------------------------------------------------
# Identity loading
# ---------------------------------------------------------------------------

def load_or_create_identity() -> tuple[dict, IdentityManager]:
    """
    Load an encrypted identity, migrate a legacy plaintext one, or create new.

    Returns (identity_dict, IdentityManager).
    Calls os._exit(1) if the user cancels the password dialog — the app
    cannot start without an identity.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    mgr = IdentityManager(DATA_DIR)

    # ── Case 1: encrypted identity on disk ──────────────────────────────
    if mgr.has_encrypted_identity():
        for attempt in range(3):
            prompt = (
                "Enter your SecretFire password to unlock your identity."
                if attempt == 0
                else f"Incorrect password (attempt {attempt + 1}/3). Try again."
            )
            pw = _prompt_password("SecretFire — Unlock Identity", prompt)
            if pw is None:
                logger.error("Password dialog cancelled — cannot start without identity.")
                os._exit(1)
            try:
                identity = mgr.load_identity(pw)
                return identity, mgr
            except ValueError:
                continue
        logger.error("Too many incorrect password attempts — exiting.")
        os._exit(1)

    # ── Case 2: legacy plaintext identity → migrate ──────────────────────
    if KEY_FILE.exists():
        try:
            with open(KEY_FILE) as f:
                legacy = json.load(f)
            logger.info("Legacy unencrypted identity found — prompting for migration.")
            pw = _prompt_password(
                "SecretFire — Protect Your Identity",
                "Your identity is currently stored unencrypted on disk.\n\n"
                "Set a password to encrypt it. If you forget this password\n"
                "your identity cannot be recovered — keep a backup.",
                confirm=True,
            )
            if pw is None:
                logger.error("Migration cancelled — cannot start without encrypting identity.")
                os._exit(1)
            identity = mgr.migrate_legacy(legacy, pw)
            KEY_FILE.unlink(missing_ok=True)
            logger.info("Legacy identity encrypted. Plaintext file removed.")
            return identity, mgr
        except Exception as e:
            logger.warning(f"Could not migrate legacy identity: {e}")

    # ── Case 3: no identity — create fresh ──────────────────────────────
    pw = _prompt_password(
        "SecretFire — Create Identity",
        "Welcome to SecretFire!\n\n"
        "Create a password to protect your identity. If you forget this\n"
        "password your identity cannot be recovered — keep a backup.",
        confirm=True,
    )
    if pw is None:
        logger.error("Password dialog cancelled — cannot create identity.")
        os._exit(1)
    identity = mgr.create_identity(pw)
    return identity, mgr


# ---------------------------------------------------------------------------
# Broadcast key (per-session ephemeral)
# ---------------------------------------------------------------------------

def generate_session_key() -> tuple[bytes, str]:
    """
    Generate a fresh AES-256 broadcast key for this session.
    Never written to disk — discarded when the process exits.
    """
    key    = crypto_utils.generate_broadcast_key()
    key_id = base64.b64encode(os.urandom(8)).decode().rstrip("=")[:8]
    return key, key_id


# ---------------------------------------------------------------------------
# Misc startup helpers
# ---------------------------------------------------------------------------

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
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def start_server(app) -> threading.Thread:
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
    try:
        from PIL import Image, ImageDraw
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([2, 2, size - 2, size - 2], fill=(0, 200, 220, 255))
        d.ellipse([10, 10, size - 10, size - 10], fill=(8, 14, 26, 255))
        d.ellipse([24, 22, 40, 38], fill=(0, 229, 255, 255))
        d.ellipse([20, 32, 44, 52], fill=(0, 180, 200, 200))
        return img
    except Exception:
        return None


def start_tray(app_url: str, tor_manager=None, window_ref=None):
    try:
        import pystray
        img = _make_tray_image()
        if not img:
            logger.warning("System tray: PIL not available — skipping tray icon")
            return

        def open_app(icon, item):
            win = window_ref[0] if window_ref else None
            if win is not None:
                try:
                    win.show()
                    return
                except Exception as e:
                    logger.warning(f"webview show() failed: {e}")
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


def open_window(port: int, window_ref=None):
    url = f"http://127.0.0.1:{port}"
    try:
        import webview
        logger.info("Opening SecretFire window…")
        window = webview.create_window(
            "SecretFire", url,
            width=1300, height=860,
            min_size=(900, 650),
            resizable=True,
        )
        if window_ref is not None:
            window_ref[0] = window

        def _on_closing():
            window.hide()
            return False

        try:
            window.events.closing += _on_closing
        except Exception:
            pass

        webview.start()
        logger.info("webview exited — app still alive via tray")
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

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
    identity, identity_manager = load_or_create_identity()

    logger.info("Generating session broadcast key...")
    broadcast_key, key_id = generate_session_key()
    logger.info(f"Session key_id: {key_id}")

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

    gossip = GossipManager(tor, identity, broadcast_key, key_id=key_id)
    gossip.start()

    app = create_app(tor, gossip, identity, identity_manager)

    logger.info(f"SecretFire running at http://127.0.0.1:{FLASK_PORT}")
    start_server(app)

    if not wait_for_server(FLASK_PORT):
        logger.warning("Server did not become ready in time — opening anyway.")

    url = f"http://127.0.0.1:{FLASK_PORT}"
    window_ref = [None]
    start_tray(url, tor, window_ref)
    _hide_console_window()
    open_window(FLASK_PORT, window_ref)


if __name__ == "__main__":
    main()
