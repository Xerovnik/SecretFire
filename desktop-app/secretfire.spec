# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — builds SecretFire into a single-file executable
# Run: pyinstaller secretfire.spec

import os
from pathlib import Path

# Include pre-downloaded Tor bundle if present (built by download_tor_bundle.py).
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
        # cryptography
        "cryptography",
        "cryptography.hazmat.primitives",
        "cryptography.hazmat.primitives.asymmetric.x25519",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "cryptography.hazmat.primitives.ciphers.aead",
        "cryptography.hazmat.primitives.kdf.hkdf",
        # argon2-cffi (identity encryption)
        "argon2",
        "argon2.low_level",
        "argon2._utils",
        "argon2._typing",
        # flask / server
        "flask",
        "flask_cors",
        "stem",
        "requests",
        "waitress",
        # tray / gui
        "pystray",
        "pystray._win32",
        "pystray._xorg",
        "pystray._darwin",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        # tkinter dialogs
        "tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.simpledialog",
        # local modules
        "updater",
        "identity",
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
    # UPX is disabled: UPX compression interferes with the Windows PE loader
    # for python3xx.dll and VC++ runtime DLLs, causing "Failed to load Python DLL"
    # / "The specified module could not be found" errors on some Windows systems.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
