# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — builds SecretFire as a one-directory bundle.
#
# ONE-DIR (not one-file) is intentional and important.
#
# The --onefile approach extracts python3xx.dll and all DLLs into a _MEI*
# temp folder on every launch.  Windows Defender, corporate AV, and partially-
# failed prior extractions routinely leave that DLL in a broken state, causing:
#
#   "Failed to load Python DLL … python311.dll.
#    LoadLibrary: The specified module could not be found."
#
# With --onedir every DLL sits permanently next to SecretFire.exe.  Windows
# locates them instantly via the standard DLL search order — no temp extraction,
# no AV interception, no stale _MEI dirs accumulating in Downloads.
#
# Distribution: zip dist/SecretFire/ → users unzip once and run SecretFire.exe.
#
# Build:
#   pip install pyinstaller
#   python download_tor_bundle.py   # optional — bundles Tor so users don't need it
#   pyinstaller secretfire.spec

import os
from pathlib import Path

# Include pre-downloaded Tor bundle if present (built by download_tor_bundle.py).
# When present, users never need to download Tor themselves — important for
# users on networks that block torproject.org (e.g. UAE, China, Russia).
tor_bundle_path = Path("tor_bundle")
tor_bundle_datas = []
if tor_bundle_path.exists():
    for f in tor_bundle_path.iterdir():
        if f.is_file():
            tor_bundle_datas.append((str(f), "tor_bundle"))
    print(f"[spec] Bundling {len(tor_bundle_datas)} Tor file(s) from {tor_bundle_path}/")
else:
    print("[spec] WARNING: tor_bundle/ not found — Tor will be downloaded at runtime")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("web", "web"),
    ] + tor_bundle_datas,
    hiddenimports=[
        "cryptography",
        "cryptography.hazmat.primitives",
        "cryptography.hazmat.primitives.asymmetric.x25519",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "cryptography.hazmat.primitives.ciphers.aead",
        "cryptography.hazmat.primitives.kdf.hkdf",
        "flask",
        "flask_cors",
        "stem",
        "requests",
        "waitress",
        "pystray",
        "pystray._win32",
        "pystray._xorg",
        "pystray._darwin",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "tkinter",
        "tkinter.filedialog",
        "updater",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=True,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],                          # binaries go to COLLECT, not embedded in exe
    exclude_binaries=True,       # required for --onedir: DLLs live beside the exe
    name="SecretFire",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SecretFire",
)
