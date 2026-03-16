# SecretFire

**Anonymous P2P microblogging over Tor.**

SecretFire is a decentralized, censorship-resistant messaging platform. It runs entirely on your local machine, routes all traffic through the Tor network, and communicates with peers through Tor hidden services — no central servers, no accounts, no surveillance.

---

## How It Works

- **No central server.** The network exists only as long as nodes are online and communicating.
- **Tor hidden services.** Your IP address is never revealed. You are identified only by your `.onion` address.
- **Ed25519 identity.** Your identity is cryptographic. A keypair is generated locally on first run and never leaves your machine.
- **Gossip protocol.** Posts are broadcast as encrypted message fragments that propagate peer-to-peer across the network.
- **AES-256-GCM encryption.** Message content is encrypted end-to-end. Only intended recipients can reassemble fragments.
- **Signed posts.** Ed25519 signatures ensure posts genuinely originate from their claimed author.
- **Bundled Tor.** SecretFire downloads the latest stable Tor binary directly from the Tor Project on first run and keeps it up to date automatically. No separate Tor installation is required.

---

## Download

Pre-built binaries are available on the [Releases](https://github.com/Xerovnik/SecretFire/releases/latest) page.

| Platform | File |
|----------|------|
| Windows  | `SecretFire-windows.exe` |
| macOS    | `SecretFire-macos` |
| Linux    | `SecretFire-linux` |

---

## Run from Source

**Requirements:** Python 3.10+, pip

```bash
git clone https://github.com/Xerovnik/SecretFire.git
cd SecretFire/desktop-app
pip install -r requirements.txt
python main.py
```

The app opens in its own standalone window. Your `.onion` address is displayed in the sidebar once Tor connects.

On first run, SecretFire will automatically download the latest Tor binary from the Tor Project and verify its integrity before starting. An internet connection is required for this step.

### Linux — standalone window dependency

On Linux the standalone window requires a system package that pip cannot install. Run this once before starting the app:

```bash
sudo apt install python3-gi gir1.2-webkit2-4.0
```

If this package is not available, the app will fall back to opening in your default browser instead — everything will still work.

---

## Build

SecretFire uses [PyInstaller](https://pyinstaller.org) to produce single-file executables.

```bash
cd desktop-app
pyinstaller secretfire.spec
```

The binary will be in `desktop-app/dist/`. GitHub Actions automatically builds for all three platforms whenever a new version tag is pushed.

---

## Architecture

```
desktop-app/
├── main.py          — entry point, orchestrates startup
├── tor_manager.py   — manages the embedded Tor process and hidden service
├── tor_updater.py   — downloads and verifies the Tor binary from the Tor Project
├── gossip.py        — P2P gossip protocol and peer sync
├── crypto_utils.py  — Ed25519 signing, AES-256-GCM encryption
├── protocol.py      — message format and fragment handling
├── storage.py       — local post and peer storage
├── api_server.py    — Flask REST API served to the local UI
├── config.py        — ports, paths, and constants
└── web/             — local frontend (HTML/CSS/JS)
```

---

## Privacy Notes

- SecretFire never connects to any server outside of the Tor network.
- The Tor binary is downloaded directly from the Tor Project and verified by SHA-256 checksum before use.
- No telemetry, no analytics, no crash reporting.
- Your keypair and posts are stored locally only.
- Peers know your `.onion` address but not your IP.

---

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE) for details.

Copyright (C) 2026 J. Zerovnik
