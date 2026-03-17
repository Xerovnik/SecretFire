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
    Does NOT start the launcher — call apply_update() for that.
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

    logger.info(f"Download complete: {tmp_path}")
    return str(tmp_path)


def apply_update(staged_path: str) -> None:
    """
    Write and immediately start the launcher script that will replace the
    current binary and restart the app.  Call this right before os._exit().

    The launcher sleeps for a few seconds (giving the current process time
    to fully exit and release any file locks) before copying and restarting.
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Auto-update only works in packaged builds.")

    new_exe = Path(staged_path).resolve()
    current_exe = Path(sys.executable).resolve()
    stage_dir = new_exe.parent

    logger.info(f"Applying update: {new_exe} → {current_exe}")

    if _current_platform() == "windows":
        _start_powershell_launcher(new_exe, current_exe, stage_dir)
    else:
        _start_shell_launcher(new_exe, current_exe, stage_dir)


def _start_powershell_launcher(new_exe: Path, current_exe: Path,
                                stage_dir: Path) -> None:
    """
    Windows: write a .ps1 script and run it hidden via PowerShell.

    Using a .ps1 file (rather than an inline -Command string) avoids all
    quoting/escaping issues with paths that contain spaces.
    PowerShell is available on every supported Windows version (7+).
    CREATE_NEW_PROCESS_GROUP ensures the child survives after os._exit().

    Strategy: rename old exe → copy new exe → start new exe.
    Windows lets you rename (Move-Item) a recently-run exe on NTFS without
    error, but Copy-Item -Force over the same path can fail with a file-lock
    error even seconds after the process exits.  Moving the old binary out of
    the way first avoids that lock entirely.
    """
    backup_exe = str(current_exe) + ".bak"
    ps1 = stage_dir / "do_update.ps1"
    # Single-quoted strings in PowerShell are literal — no variable expansion,
    # safe even when paths contain spaces or special characters.
    ps1.write_text(
        "Start-Sleep -Seconds 6\n"
        # Remove any leftover backup from a previous failed update attempt
        f"if (Test-Path -LiteralPath '{backup_exe}') {{ Remove-Item -Force -LiteralPath '{backup_exe}' }}\n"
        # Rename old exe to .bak — always succeeds on NTFS, avoids overwrite lock
        f"Move-Item -LiteralPath '{current_exe}' -Destination '{backup_exe}' -ErrorAction SilentlyContinue\n"
        # Copy new binary into the now-vacant original path
        f"Copy-Item -Force -Path '{new_exe}' -Destination '{current_exe}'\n"
        # Brief pause — ensures Windows has fully flushed the copied exe to disk
        # before we try to execute it (avoids "Python DLL" load errors on first launch)
        "Start-Sleep -Seconds 2\n"
        # Launch updated app from its own directory so relative paths resolve correctly
        f"Start-Process -FilePath '{current_exe}' -WorkingDirectory '{current_exe.parent}'\n"
        # Give the new app a moment to start, then clean up
        "Start-Sleep -Seconds 3\n"
        f"Remove-Item -Force -LiteralPath '{backup_exe}' -ErrorAction SilentlyContinue\n"
        "Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue\n",
        encoding="utf-8",
    )
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass",
            "-File", str(ps1),
        ],
        # CREATE_NEW_PROCESS_GROUP: child gets its own group → survives parent exit
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info("PowerShell launcher started — exiting now.")


def _start_shell_launcher(new_exe: Path, current_exe: Path,
                           stage_dir: Path) -> None:
    """Linux / macOS: write a .sh script and start it in its own session."""
    script = stage_dir / "do_update.sh"
    script.write_text(
        "#!/bin/sh\n"
        "sleep 4\n"
        f"cp -f '{new_exe}' '{current_exe}'\n"
        f"'{current_exe}' &\n"
        "rm -- \"$0\"\n",
        encoding="utf-8",
    )
    os.chmod(script, 0o755)
    subprocess.Popen(
        ["/bin/sh", str(script)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,  # detach from parent's process group
    )
    logger.info("Shell launcher started — exiting now.")
