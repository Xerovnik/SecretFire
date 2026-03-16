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
TorUpdater — downloads and keeps the Tor binary up to date from the
official Tor Project archive.  The app will not run more than one
release behind the latest stable Tor Browser / Expert Bundle release.

Download source : https://archive.torproject.org/tor-package-archive/torbrowser/
Version check   : https://aus1.torproject.org/torbrowser/update_3/release/downloads.json
Integrity check : SHA-256 against the official sha256sums-unsigned-build.txt
"""

import hashlib
import io
import logging
import os
import platform
import sys
import tarfile
import threading
import time
import zipfile
from pathlib import Path

import requests

from config import TOR_BIN_DIR

logger = logging.getLogger("tor_updater")

VERSION_CHECK_URL = (
    "https://aus1.torproject.org/torbrowser/update_3/release/downloads.json"
)
ARCHIVE_BASE = (
    "https://archive.torproject.org/tor-package-archive/torbrowser"
)
VERSION_FILE = TOR_BIN_DIR / "version.txt"

# How often to re-check in the background (seconds)
CHECK_INTERVAL = 60 * 60 * 24  # 24 hours

# How many releases behind is acceptable before forcing an update
MAX_RELEASES_BEHIND = 1


def _platform_info() -> tuple[str, str, str]:
    """
    Returns (bundle_platform_string, tor_executable_name, os_key_in_json).
    """
    machine = platform.machine().lower()
    if sys.platform == "win32":
        return "windows-x86_64", "tor.exe", "win64"
    elif sys.platform == "darwin":
        arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
        return f"macos-{arch}", "tor", "osx"
    else:
        return "linux-x86_64", "tor", "linux64"


def get_bundled_tor_path() -> Path | None:
    """Return path to the locally managed Tor binary if it exists."""
    _, exe_name, _ = _platform_info()
    path = TOR_BIN_DIR / exe_name
    return path if path.exists() else None


def get_local_version() -> str | None:
    """Return the version string of the locally stored Tor binary."""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return None


def get_latest_version() -> str:
    """Fetch the latest stable Tor Browser version from the Tor Project API."""
    resp = requests.get(VERSION_CHECK_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    version = data.get("version")
    if not version:
        raise ValueError(f"Unexpected response from version API: {data!r}")
    return version


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a dotted version string into a comparable tuple of ints."""
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


def releases_behind(local: str, latest: str) -> int:
    """
    Return how many minor/patch releases the local version is behind latest.
    We compare the last two components of the version tuple (minor.patch).
    Returns 0 if local >= latest.
    """
    lv = _parse_version(local)
    rv = _parse_version(latest)
    if rv <= lv:
        return 0
    # Treat each unique version as one release
    return 1 if rv > lv else 0


def _fetch_sha256_map(version: str) -> dict[str, str]:
    """
    Download the official SHA-256 sums file and return a filename→hash dict.
    """
    url = f"{ARCHIVE_BASE}/{version}/sha256sums-unsigned-build.txt"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    result: dict[str, str] = {}
    for line in resp.text.splitlines():
        parts = line.split()
        if len(parts) == 2:
            digest, name = parts
            result[name.lstrip("*")] = digest
    return result


def _download_and_verify(version: str) -> Path:
    """
    Download the Tor Expert Bundle for this platform, verify its SHA-256,
    extract the tor binary (and any required shared libraries), and return
    the path to the tor executable.
    """
    platform_str, exe_name, _ = _platform_info()
    filename = f"tor-expert-bundle-{platform_str}-{version}.tar.gz"
    url = f"{ARCHIVE_BASE}/{version}/{filename}"

    logger.info(f"Fetching SHA-256 manifest for Tor {version}…")
    sha256_map = _fetch_sha256_map(version)
    expected_hash = sha256_map.get(filename)
    if not expected_hash:
        raise ValueError(
            f"Could not find '{filename}' in Tor Project SHA-256 manifest."
        )

    logger.info(f"Downloading {filename} from Tor Project…")
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()

    buf = bytearray()
    for chunk in resp.iter_content(chunk_size=65536):
        buf.extend(chunk)
    data = bytes(buf)

    actual_hash = hashlib.sha256(data).hexdigest()
    if actual_hash.lower() != expected_hash.lower():
        raise ValueError(
            f"SHA-256 mismatch for {filename}!\n"
            f"  expected : {expected_hash}\n"
            f"  actual   : {actual_hash}\n"
            "Refusing to install — binary may be corrupt or tampered with."
        )
    logger.info("SHA-256 verified successfully.")

    TOR_BIN_DIR.mkdir(parents=True, exist_ok=True)

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for member in tf.getmembers():
            # Extract everything inside the tor/ directory
            if member.name.startswith("tor/") and not member.isdir():
                bare_name = Path(member.name).name
                dest = TOR_BIN_DIR / bare_name
                f = tf.extractfile(member)
                if f:
                    dest.write_bytes(f.read())
                    if not sys.platform == "win32":
                        dest.chmod(0o755 if bare_name == exe_name else 0o644)

    tor_path = TOR_BIN_DIR / exe_name
    if not tor_path.exists():
        raise FileNotFoundError(
            f"Extracted archive but could not find '{exe_name}' in {TOR_BIN_DIR}"
        )

    VERSION_FILE.write_text(version)
    logger.info(f"Tor {version} installed to {tor_path}")
    return tor_path


def check_and_update(force: bool = False) -> Path | None:
    """
    Check whether the locally stored Tor binary is up to date.
    Downloads a new version if:
      - No local binary exists, or
      - The local version is more than MAX_RELEASES_BEHIND behind latest, or
      - force=True is passed.

    Returns the path to the (possibly freshly installed) Tor binary,
    or None if the download fails and no local binary exists.
    """
    try:
        latest = get_latest_version()
        local = get_local_version()
        logger.info(
            f"Tor version check — local: {local or 'none'}, latest: {latest}"
        )

        behind = releases_behind(local, latest) if local else MAX_RELEASES_BEHIND + 1

        if force or not get_bundled_tor_path() or behind > MAX_RELEASES_BEHIND:
            if behind > MAX_RELEASES_BEHIND:
                logger.warning(
                    f"Local Tor ({local}) is {behind} release(s) behind "
                    f"latest ({latest}) — updating now."
                )
            return _download_and_verify(latest)
        else:
            logger.info("Tor binary is up to date.")
            return get_bundled_tor_path()

    except Exception as exc:
        logger.warning(f"Tor update check failed: {exc}")
        existing = get_bundled_tor_path()
        if existing:
            logger.info(f"Continuing with existing Tor binary: {existing}")
        else:
            logger.warning(
                "No local Tor binary available — will fall back to system Tor or demo mode."
            )
        return existing


def start_background_updater() -> None:
    """
    Spawn a daemon thread that re-checks for Tor updates every CHECK_INTERVAL
    seconds.  The thread only downloads if an update is actually needed.
    """

    def _loop():
        while True:
            time.sleep(CHECK_INTERVAL)
            logger.info("Background Tor update check starting…")
            check_and_update()

    t = threading.Thread(target=_loop, daemon=True, name="tor-updater")
    t.start()
    logger.info(
        f"Tor update checker scheduled (interval: {CHECK_INTERVAL // 3600}h)."
    )


def get_tor_env() -> dict:
    """
    Return environment variables needed to run the downloaded Tor binary.
    On Linux the bundled shared libraries live alongside the binary, so we
    prepend TOR_BIN_DIR to LD_LIBRARY_PATH.
    """
    env = os.environ.copy()
    if sys.platform not in ("win32", "darwin"):
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = (
            f"{TOR_BIN_DIR}:{existing}" if existing else str(TOR_BIN_DIR)
        )
    return env
