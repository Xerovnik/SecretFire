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
Auto-update logic for SecretFire.

Checks the GitHub Releases API for a newer version, downloads the matching
binary for the current platform, then writes a small launcher script that
swaps the executable and restarts the app once the current process exits.
"""

import os
import sys
import logging
import platform
import subprocess
from pathlib import Path

import requests
from config import APP_VERSION

logger = logging.getLogger("updater")

GITHUB_RELEASES_API = "https://api.github.com/repos/Xerovnik/SecretFire/releases/latest"

_PLATFORM_ASSET = {
    "windows": "SecretFire-windows.exe",
    "linux":   "SecretFire-linux",
    "darwin":  "SecretFire-macos",
}


def _current_platform() -> str:
    return platform.system().lower()


def _asset_name() -> str | None:
    return _PLATFORM_ASSET.get(_current_platform())


def _version_newer(v_new: str, v_old: str) -> bool:
    try:
        def parse(v):
            return tuple(int(x) for x in v.strip().lstrip("v").split("."))
        return parse(v_new) > parse(v_old)
    except Exception:
        return False


def check_for_update() -> dict | None:
    """
    Query GitHub for the latest release.

    Returns a dict:
      { update_available, current, latest, tag, download_url, changelog, release_url }
    or None if the check could not be completed.
    """
    try:
        resp = requests.get(GITHUB_RELEASES_API, timeout=12,
                            headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
        data = resp.json()

        latest_tag = data.get("tag_name", "")
        latest_ver = latest_tag.lstrip("v")

        asset_name = _asset_name()
        download_url = None
        if asset_name:
            for asset in data.get("assets", []):
                if asset["name"] == asset_name:
                    download_url = asset["browser_download_url"]
                    break

        if _version_newer(latest_ver, APP_VERSION):
            return {
                "update_available": True,
                "current": APP_VERSION,
                "latest": latest_ver,
                "tag": latest_tag,
                "download_url": download_url,
                "changelog": data.get("body", ""),
                "release_url": data.get("html_url", ""),
            }
        else:
            return {
                "update_available": False,
                "current": APP_VERSION,
                "latest": latest_ver,
            }

    except Exception as e:
        logger.warning(f"Update check failed: {e}")
        return None


def download_update(download_url: str, progress_cb=None) -> str:
    """
    Download the new binary to a staging directory next to the current exe.

    progress_cb(pct: int) is called with 0-100 during the download.
    Returns the path to the downloaded file.
    Raises RuntimeError if not running as a frozen (PyInstaller) build.
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError(
            "Auto-update only works in packaged builds. "
            "In development, update via git pull."
        )

    current_exe = Path(sys.executable).resolve()
    stage_dir = current_exe.parent / ".sf_update"
    stage_dir.mkdir(parents=True, exist_ok=True)

    suffix = current_exe.suffix
    tmp_path = stage_dir / f"SecretFire_new{suffix}"

    logger.info(f"Downloading update → {tmp_path}")

    resp = requests.get(download_url, stream=True, timeout=120)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0

    with open(tmp_path, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                fh.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total:
                    progress_cb(min(99, int(downloaded * 100 / total)))

    if progress_cb:
        progress_cb(100)

    if _current_platform() != "windows":
        os.chmod(tmp_path, 0o755)

    _write_launcher(tmp_path, current_exe)
    return str(tmp_path)


def _write_launcher(new_exe: Path, current_exe: Path) -> None:
    """
    Write a small script that waits for this process to exit, replaces the
    executable, and restarts the app.  Launch the script detached so it
    survives after we call sys.exit().
    """
    pid = os.getpid()
    stage_dir = new_exe.parent

    if _current_platform() == "windows":
        script = stage_dir / "do_update.bat"
        script.write_text(
            "@echo off\n"
            f":wait\n"
            f"tasklist /FI \"PID eq {pid}\" 2>nul | find \"{pid}\" >nul\n"
            f"if not errorlevel 1 (timeout /t 1 /nobreak >nul && goto wait)\n"
            f"copy /y \"{new_exe}\" \"{current_exe}\"\n"
            f"start \"\" \"{current_exe}\"\n"
            "del \"%~f0\"\n",
            encoding="utf-8",
        )
        subprocess.Popen(
            ["cmd.exe", "/c", str(script)],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
    else:
        script = stage_dir / "do_update.sh"
        script.write_text(
            "#!/bin/sh\n"
            f"while kill -0 {pid} 2>/dev/null; do sleep 1; done\n"
            f"cp -f '{new_exe}' '{current_exe}'\n"
            f"'{current_exe}' &\n"
            "rm -- \"$0\"\n",
            encoding="utf-8",
        )
        os.chmod(script, 0o755)
        subprocess.Popen(
            ["/bin/sh", str(script)],
            close_fds=True,
            start_new_session=True,
        )

    logger.info("Launcher script written and started.")
