"""
TorManager — manages the embedded Tor process and hidden service.

Falls back gracefully to a no-Tor demo mode so the app works without Tor installed.
"""

import os
import time
import shutil
import threading
import subprocess
import logging
from pathlib import Path
from config import (
    TOR_DATA_DIR, TOR_HIDDEN_SERVICE_DIR,
    TOR_SOCKS_PORT, TOR_CONTROL_PORT, TOR_HIDDEN_SERVICE_PORT,
    FLASK_PORT
)

logger = logging.getLogger("tor_manager")


class TorManager:
    def __init__(self):
        self.process = None
        self.onion_address = None
        self.socks_port = TOR_SOCKS_PORT
        self.control_port = TOR_CONTROL_PORT
        self.is_running = False
        self.demo_mode = False
        self._lock = threading.Lock()

    def _find_tor(self) -> str | None:
        return shutil.which("tor")

    def _write_torrc(self) -> Path:
        TOR_DATA_DIR.mkdir(parents=True, exist_ok=True)
        TOR_HIDDEN_SERVICE_DIR.mkdir(parents=True, exist_ok=True)

        torrc_path = TOR_DATA_DIR / "torrc"
        torrc_content = f"""
SocksPort {self.socks_port}
ControlPort {self.control_port}
DataDirectory {TOR_DATA_DIR}
HiddenServiceDir {TOR_HIDDEN_SERVICE_DIR}
HiddenServicePort 80 127.0.0.1:{TOR_HIDDEN_SERVICE_PORT}
Log notice stdout
RelayBandwidthRate 100 KB
RelayBandwidthBurst 200 KB
ORPort auto
ExitPolicy reject *:*
"""
        torrc_path.write_text(torrc_content.strip())
        return torrc_path

    def start(self) -> bool:
        tor_bin = self._find_tor()
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
                break
            logger.debug(f"[Tor] {line.strip()}")
            if "Bootstrapped 100%" in line or "Done" in line:
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
