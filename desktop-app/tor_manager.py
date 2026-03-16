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
TorManager — manages the embedded Tor process and hidden service.

Falls back gracefully to a no-Tor demo mode so the app works without Tor installed.
"""

import os
import time
import shutil
import socket
import threading
import subprocess
import logging
from pathlib import Path
from config import (
    TOR_DATA_DIR, TOR_HIDDEN_SERVICE_DIR,
    TOR_SOCKS_PORT, TOR_HIDDEN_SERVICE_PORT,
    FLASK_PORT
)
from tor_updater import get_bundled_tor_path, get_tor_env

logger = logging.getLogger("tor_manager")


def _find_free_port(preferred: int) -> int:
    """Try preferred port first; fall back through 19150-19200 if it's taken."""
    for port in [preferred] + list(range(19150, 19200)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                if port != preferred:
                    logger.warning(
                        f"Port {preferred} in use (system Tor?), using fallback port {port}"
                    )
                return port
            except OSError:
                continue
    # Last resort: let the OS assign any free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        logger.warning(f"All preferred ports taken, using OS-assigned port {port}")
        return port


class TorManager:
    def __init__(self):
        self.process = None
        self.onion_address = None
        self.socks_port = _find_free_port(TOR_SOCKS_PORT)
        self.is_running = False
        self.demo_mode = False
        self._lock = threading.Lock()

    def _find_tor(self) -> tuple[str | None, dict]:
        bundled = get_bundled_tor_path()
        if bundled:
            logger.info(f"Using bundled Tor binary: {bundled}")
            return str(bundled), get_tor_env()
        system = shutil.which("tor")
        if system:
            logger.info(f"Using system Tor binary: {system}")
            return system, os.environ.copy()
        return None, {}

    def _clear_stale_lock(self):
        lock = TOR_DATA_DIR / "lock"
        if lock.exists():
            try:
                lock.unlink()
                logger.info("Removed stale Tor lock file")
            except OSError as e:
                logger.warning(f"Could not remove stale lock file: {e}")

    def _write_torrc(self) -> Path:
        TOR_DATA_DIR.mkdir(parents=True, exist_ok=True)
        TOR_DATA_DIR.chmod(0o700)
        TOR_HIDDEN_SERVICE_DIR.mkdir(parents=True, exist_ok=True)
        TOR_HIDDEN_SERVICE_DIR.chmod(0o700)
        self._clear_stale_lock()

        torrc_path = TOR_DATA_DIR / "torrc"
        torrc_content = f"""
SocksPort {self.socks_port}
DataDirectory {TOR_DATA_DIR}
HiddenServiceDir {TOR_HIDDEN_SERVICE_DIR}
HiddenServicePort 80 127.0.0.1:{TOR_HIDDEN_SERVICE_PORT}
Log notice stdout
Sandbox 0
"""
        torrc_path.write_text(torrc_content.strip())
        return torrc_path

    def start(self) -> bool:
        tor_bin, tor_env = self._find_tor()
        if not tor_bin:
            logger.warning("Tor not found — running in demo mode (no anonymity)")
            self.demo_mode = True
            self.onion_address = "demo-mode-no-tor.local"
            self.is_running = True
            return True

        torrc = self._write_torrc()
        try:
            self.process = subprocess.Popen(
                [tor_bin, "-f", str(torrc)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=tor_env,
            )
            logger.info(f"Tor started with PID {self.process.pid}")
            self._wait_for_bootstrap()
            self._read_onion_address()
            self.is_running = True
            return True
        except Exception as e:
            logger.error(f"Failed to start Tor: {e}")
            self.demo_mode = True
            self.onion_address = "demo-mode-tor-failed.local"
            self.is_running = True
            return True

    def _wait_for_bootstrap(self, timeout=120):
        if not self.process:
            return
        start = time.time()
        while time.time() - start < timeout:
            line = self.process.stdout.readline()
            if not line:
                if self.process.poll() is not None:
                    remaining = self.process.stdout.read()
                    if remaining:
                        for l in remaining.splitlines():
                            logger.warning(f"[Tor] {l}")
                    logger.warning(f"Tor process exited early (code {self.process.returncode})")
                    break
                time.sleep(0.1)
                continue
            logger.info(f"[Tor] {line.strip()}")
            if "Bootstrapped 100%" in line:
                logger.info("Tor bootstrapped successfully")
                return
            if "Problem bootstrapping" in line:
                logger.warning(f"Tor bootstrap issue: {line.strip()}")
        logger.warning("Tor bootstrap timeout")

    def _read_onion_address(self):
        hostname_file = TOR_HIDDEN_SERVICE_DIR / "hostname"
        for _ in range(30):
            if hostname_file.exists():
                self.onion_address = hostname_file.read_text().strip()
                logger.info(f"Hidden service: {self.onion_address}")
                return
            time.sleep(2)
        logger.warning("Could not read onion address")
        self.onion_address = "unknown.onion"

    def get_proxies(self) -> dict | None:
        if self.demo_mode or not self.is_running:
            return None
        return {
            "http": f"socks5h://127.0.0.1:{self.socks_port}",
            "https": f"socks5h://127.0.0.1:{self.socks_port}",
        }

    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
        self.is_running = False

    def status(self) -> dict:
        return {
            "running": self.is_running,
            "demo_mode": self.demo_mode,
            "onion_address": self.onion_address,
            "socks_port": self.socks_port if not self.demo_mode else None,
        }
