# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — builds SecretFire into a single-file executable
# Run: pyinstaller secretfire.spec

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("web", "web"),
    ],
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
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
