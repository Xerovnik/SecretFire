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

Connection strategy (fully automatic, no user action required):
  1. Try a direct Tor connection (30 s bootstrap window).
  2. On failure: request fresh obfs4 bridges from Tor Project's Moat API.
  3. If Moat is unreachable: fall back to hardcoded default bridges.
  4. Retry Tor with bridges (60 s bootstrap window).
  5. If still failing: run in demo mode (local only, no anonymity).

obfs4 disguises Tor traffic as random encrypted bytes — identical security
to vanilla Tor, just harder for routers and ISPs to fingerprint and block.
"""

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import logging
from pathlib import Path

import requests

from config import (
    TOR_DATA_DIR, TOR_HIDDEN_SERVICE_DIR, TOR_BIN_DIR,
    TOR_SOCKS_PORT, FLASK_PORT,
)
from tor_updater import get_bundled_tor_path, get_tor_env

logger = logging.getLogger("tor_manager")

# ---------------------------------------------------------------------------
# Bridge fallback configuration
# ---------------------------------------------------------------------------

# Tor Project's Moat API — returns fresh obfs4 bridge lines on demand.
_MOAT_URL = "https://bridges.torproject.org/moat/circumvention/default"

# Hardcoded Tor Browser default bridges (last-resort fallback if Moat is
# unreachable).  These are the same bridges shipped with Tor Browser and are
# public knowledge — using them does not weaken anonymity.
_DEFAULT_BRIDGES = [
    "obfs4 193.11.166.194:27015 2D82C2E354D531A68469ADF7F878055D672057DD cert=4TLQPJrTSaDffMK7Nbao6LC7G9OW/NHkUwIdjLSS3KYf06igoeW6Fx84m9sZ1NdopMJaxw iat-mode=0",
    "obfs4 37.218.245.14:38224 D9A82D2F9C2F65A18407B1D2B764F130847F8B5D cert=bjRh2T8nW11yn+n+T2Yc4Ysm5Am+9SHeD/LgD7G9kW5GOffiVQKqYMaQp+2DzNoAIQINlg iat-mode=0",
    "obfs4 85.31.186.98:443 011F2599C0E9B27EE74B353155E244813763C3E5 cert=ayq0XzCwhpdysn5o0EyDUbmSOx3X/oTEbzDMvK8sB8WvFaoduf3VC/oJRuMqpFCa4ZqYXA iat-mode=0",
    "obfs4 85.31.186.26:443 91A6354697E6B02A386312F68D82CF86824D3606 cert=G/gI9N+BPET1b7b7pJ+zyFGGFiGKkSdBbJy+RWCB92HNVePBTcqVVZGH3uo9JLINpnG3g iat-mode=0",
    "obfs4 193.11.166.194:27020 FDFD131ABCA63A0C76E0E06E009FA3DB87E91C8B cert=N86L9GHJkCsBAzexLfXqQaRlHaak5DI5337q6BdGLjOlx62vMLMDrjDjkUd55LRQBBGQXQ iat-mode=0",
    "obfs4 209.148.46.65:443 74FAD13168806246602538555B5521A0383A1875 cert=ssH+9rP8dG2NLDN2XuFw63hIO/9MNNinLmxQDpVa+7kTOa9/m+AGS4aCMSf96h2KMXEayA iat-mode=0",
    "obfs4 146.57.248.225:22 10A6CD36A537FCE513A322361547444B393989F0 cert=K1gDtDAIcUfeLqbstggjIos/co/2DqnervjhMi3I7+HFoYM9PmVZMn8hujHyDDU5w5F0Cg iat-mode=0",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        logger.warning(f"All preferred ports taken, using OS-assigned port {port}")
        return port


def _fetch_bridges_from_moat() -> list[str]:
    """
    Ask Tor Project's Moat API for fresh obfs4 bridge lines.
    Returns an empty list if the request fails for any reason.
    """
    try:
        resp = requests.post(
            _MOAT_URL,
            json={"type": "obfs4"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        bridges = (
            data.get("bridges", {}).get("bridge_strings", [])
            or data.get("bridge_strings", [])
        )
        if bridges:
            logger.info(f"Fetched {len(bridges)} fresh bridge(s) from Moat API")
            return bridges
    except Exception as exc:
        logger.warning(f"Moat API unavailable ({exc}) — will use hardcoded bridges")
    return []


# ---------------------------------------------------------------------------
# TorManager
# ---------------------------------------------------------------------------

class TorManager:
    def __init__(self):
        self.process = None
        self.onion_address = None
        self.socks_port = _find_free_port(TOR_SOCKS_PORT)
        self.is_running = False
        self.demo_mode = False
        self.using_bridges = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Binary / PT discovery
    # ------------------------------------------------------------------

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

    def _find_pt_binary(self) -> Path | None:
        """
        Find the obfs4 pluggable transport binary.
        Recent Tor Expert Bundles ship it as 'lyrebird'; older ones as 'obfs4proxy'.
        """
        candidates = ["lyrebird", "obfs4proxy"]
        if sys.platform == "win32":
            candidates = [f"{c}.exe" for c in candidates]
        for name in candidates:
            path = TOR_BIN_DIR / name
            if path.exists():
                logger.debug(f"Found PT binary: {path}")
                return path
        logger.warning(
            "obfs4 pluggable transport binary not found in bundle — bridge fallback unavailable"
        )
        return None

    # ------------------------------------------------------------------
    # torrc writing
    # ------------------------------------------------------------------

    def _kill_orphan_tor(self) -> None:
        """Kill any Tor process left running by a previous app instance."""
        try:
            if platform.system() == "Windows":
                # Kill by image name — only affects tor.exe, not system processes
                result = subprocess.run(
                    ["taskkill", "/f", "/im", "tor.exe"],
                    capture_output=True, timeout=8,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode == 0:
                    logger.info("Killed orphaned tor.exe process")
            else:
                # Kill by matching the bundled tor binary path
                tor_path = str(TOR_BIN_DIR)
                subprocess.run(
                    ["pkill", "-f", tor_path],
                    capture_output=True, timeout=8,
                )
                logger.info("Killed orphaned Tor process (Unix)")
            time.sleep(0.8)  # give the OS time to release the lock file
        except Exception as e:
            logger.warning(f"Could not kill orphan Tor process: {e}")

    def _clear_stale_lock(self):
        lock = TOR_DATA_DIR / "lock"
        if lock.exists():
            try:
                lock.unlink()
                logger.info("Removed stale Tor lock file")
            except OSError as e:
                logger.warning(f"Could not remove stale lock file: {e}")
                # Lock is held by a running process — kill it and retry once
                self._kill_orphan_tor()
                try:
                    lock.unlink()
                    logger.info("Removed stale Tor lock file after killing orphan")
                except OSError:
                    logger.warning("Still cannot remove lock file — Tor may fail to start")

    def _write_torrc(self, bridges: list[str] | None = None) -> Path:
        TOR_DATA_DIR.mkdir(parents=True, exist_ok=True)
        TOR_DATA_DIR.chmod(0o700)
        TOR_HIDDEN_SERVICE_DIR.mkdir(parents=True, exist_ok=True)
        TOR_HIDDEN_SERVICE_DIR.chmod(0o700)
        self._clear_stale_lock()

        bridge_block = ""
        if bridges:
            pt_bin = self._find_pt_binary()
            if pt_bin:
                bridge_lines = "\n".join(f"Bridge {b}" for b in bridges)
                bridge_block = (
                    f"\nUseBridges 1\n"
                    f"ClientTransportPlugin obfs4 exec {pt_bin}\n"
                    f"{bridge_lines}\n"
                )
            else:
                logger.warning("Skipping bridge config — PT binary not found")

        torrc_path = TOR_DATA_DIR / "torrc"
        torrc_content = (
            f"SocksPort {self.socks_port}\n"
            f"DataDirectory {TOR_DATA_DIR}\n"
            f"HiddenServiceDir {TOR_HIDDEN_SERVICE_DIR}\n"
            f"HiddenServicePort 80 127.0.0.1:{FLASK_PORT}\n"
            f"Log notice stdout\n"
            f"Sandbox 0"
            f"{bridge_block}"
        )
        torrc_path.write_text(torrc_content)
        return torrc_path

    # ------------------------------------------------------------------
    # Process management
    # ------------------------------------------------------------------

    def _launch_tor(self, tor_bin: str, torrc: Path, tor_env: dict) -> bool:
        """Start the Tor process and wait for bootstrap. Returns True on success."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait()

        # On Windows, suppress the blank console window that would otherwise
        # appear for every child process launched from a GUI (console=False) binary.
        _flags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            _flags = subprocess.CREATE_NO_WINDOW

        self.process = subprocess.Popen(
            [tor_bin, "-f", str(torrc)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=tor_env,
            creationflags=_flags,
        )
        logger.info(f"Tor started with PID {self.process.pid}")

        timeout = 60 if self.using_bridges else 30
        return self._wait_for_bootstrap(timeout=timeout)

    def start(self) -> bool:
        tor_bin, tor_env = self._find_tor()
        if not tor_bin:
            logger.warning("Tor not found — running in demo mode (no anonymity)")
            self._set_demo_mode("demo-mode-no-tor.local")
            return True

        try:
            # --- Attempt 1: direct connection ---
            logger.info("Attempting direct Tor connection…")
            torrc = self._write_torrc()
            success = self._launch_tor(tor_bin, torrc, tor_env)

            if not success:
                logger.warning(
                    "Direct Tor connection failed — attempting bridge fallback (obfs4)"
                )
                self.using_bridges = True

                # Try to get fresh bridges; fall back to hardcoded
                bridges = _fetch_bridges_from_moat() or _DEFAULT_BRIDGES

                torrc = self._write_torrc(bridges=bridges)
                pt_bin = self._find_pt_binary()

                if pt_bin:
                    logger.info(
                        f"Retrying Tor with {len(bridges)} obfs4 bridge(s) via {pt_bin.name}…"
                    )
                    success = self._launch_tor(tor_bin, torrc, tor_env)
                else:
                    logger.warning(
                        "Bridge retry skipped — obfs4 binary unavailable in bundle"
                    )

            if not success:
                logger.error(
                    "Tor failed to bootstrap (direct and bridge both failed). "
                    "Running in demo mode — messages are NOT anonymous."
                )
                self._set_demo_mode("demo-mode-tor-failed.local")
                self.is_running = True
                return True

            self._read_onion_address()
            self.is_running = True
            return True

        except Exception as e:
            logger.error(f"Failed to start Tor: {e}")
            self._set_demo_mode("demo-mode-tor-failed.local")
            return True

    def _set_demo_mode(self, addr: str):
        self.demo_mode = True
        self.onion_address = addr
        self.is_running = True

    # ------------------------------------------------------------------
    # Bootstrap monitoring
    # ------------------------------------------------------------------

    def _wait_for_bootstrap(self, timeout: int = 30) -> bool:
        """
        Read Tor stdout until bootstrap reaches 100% or timeout elapses.
        Returns True on success, False on failure/timeout.
        """
        if not self.process:
            return False

        start = time.time()
        while time.time() - start < timeout:
            line = self.process.stdout.readline()
            if not line:
                if self.process.poll() is not None:
                    remaining = self.process.stdout.read()
                    for l in (remaining or "").splitlines():
                        logger.warning(f"[Tor] {l}")
                    logger.warning(
                        f"Tor process exited early (code {self.process.returncode})"
                    )
                    return False
                time.sleep(0.1)
                continue

            logger.info(f"[Tor] {line.strip()}")

            if "Bootstrapped 100%" in line:
                logger.info("Tor bootstrapped successfully" +
                            (" (via bridges)" if self.using_bridges else ""))
                return True

            if "Problem bootstrapping" in line:
                logger.warning(f"Tor bootstrap problem: {line.strip()}")

        logger.warning(f"Tor bootstrap timed out after {timeout}s")
        return False

    # ------------------------------------------------------------------
    # Onion address
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

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
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
            self.process = None
        self.is_running = False
        lock = TOR_DATA_DIR / "lock"
        if lock.exists():
            try:
                lock.unlink()
                logger.info("Removed Tor lock file on clean shutdown")
            except Exception as e:
                logger.warning(f"Could not remove Tor lock file on shutdown: {e}")

    def status(self) -> dict:
        return {
            "running": self.is_running,
            "demo_mode": self.demo_mode,
            "using_bridges": self.using_bridges,
            "onion_address": self.onion_address,
            "socks_port": self.socks_port if not self.demo_mode else None,
        }
