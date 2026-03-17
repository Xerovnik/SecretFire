#!/usr/bin/env python3
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
Pre-download the Tor Expert Bundle for the current build platform.
Run this script during CI (before PyInstaller) to embed Tor in the app.

Saves all binaries from the tor/ directory of the Expert Bundle to ./tor_bundle/
so PyInstaller can include them as data files.  Users then never need to
download Tor themselves — important for users behind censored networks.
"""

import hashlib
import io
import os
import platform
import sys
import tarfile
from pathlib import Path

import requests

ARCHIVE_BASE = "https://archive.torproject.org/tor-package-archive/torbrowser"
VERSION_CHECK_URL = (
    "https://aus1.torproject.org/torbrowser/update_3/release/downloads.json"
)
OUT_DIR = Path(__file__).parent / "tor_bundle"


def get_platform() -> tuple[str, str]:
    machine = platform.machine().lower()
    if sys.platform == "win32":
        return "windows-x86_64", "tor.exe"
    elif sys.platform == "darwin":
        arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
        return f"macos-{arch}", "tor"
    else:
        return "linux-x86_64", "tor"


def main():
    OUT_DIR.mkdir(exist_ok=True)
    platform_str, exe_name = get_platform()

    print(f"Platform: {platform_str}")

    # Fetch latest version
    print("Checking latest Tor version...")
    resp = requests.get(VERSION_CHECK_URL, timeout=30)
    resp.raise_for_status()
    version = resp.json()["version"]
    print(f"Latest Tor version: {version}")

    filename = f"tor-expert-bundle-{platform_str}-{version}.tar.gz"
    url = f"{ARCHIVE_BASE}/{version}/{filename}"

    # Fetch SHA256 manifest
    sha_url = f"{ARCHIVE_BASE}/{version}/sha256sums-unsigned-build.txt"
    print("Fetching SHA256 manifest...")
    sha_resp = requests.get(sha_url, timeout=30)
    sha_resp.raise_for_status()
    sha_map: dict[str, str] = {}
    for line in sha_resp.text.splitlines():
        parts = line.split()
        if len(parts) == 2:
            sha_map[parts[1].lstrip("*")] = parts[0]
    expected = sha_map.get(filename)
    if not expected:
        raise ValueError(f"SHA256 not found in manifest for '{filename}'")

    # Download bundle
    print(f"Downloading {url} ...")
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    buf = bytearray()
    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    for chunk in resp.iter_content(65536):
        buf.extend(chunk)
        downloaded += len(chunk)
        if total:
            pct = downloaded * 100 // total
            print(f"\r  {pct}% ({downloaded // 1024} KB)", end="", flush=True)
    print()
    data = bytes(buf)

    # Verify integrity
    actual = hashlib.sha256(data).hexdigest()
    if actual.lower() != expected.lower():
        raise ValueError(
            f"SHA256 mismatch for {filename}!\n"
            f"  expected : {expected}\n"
            f"  actual   : {actual}"
        )
    print("SHA256 verified OK")

    # Extract
    _EXECUTABLES = {exe_name, "lyrebird", "obfs4proxy", "snowflake-client",
                    "lyrebird.exe", "obfs4proxy.exe", "snowflake-client.exe",
                    "tor-gencert"}
    print(f"Extracting to {OUT_DIR}/...")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for member in tf.getmembers():
            if member.name.startswith("tor/") and not member.isdir():
                bare = Path(member.name).name
                dest = OUT_DIR / bare
                f = tf.extractfile(member)
                if f:
                    dest.write_bytes(f.read())
                    if sys.platform != "win32":
                        dest.chmod(0o755 if bare in _EXECUTABLES else 0o644)
                    print(f"  {bare}")

    # Write version marker
    (OUT_DIR / "version.txt").write_text(version)

    # Sanity-check
    tor_exe = OUT_DIR / exe_name
    if not tor_exe.exists():
        raise FileNotFoundError(
            f"Extraction completed but '{exe_name}' not found in {OUT_DIR}"
        )

    print(f"\nTor {version} bundled successfully -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
