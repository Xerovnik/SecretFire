# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — builds SecretFire into a single-file executable
# Run: pyinstaller secretfire.spec

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
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SecretFire",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
