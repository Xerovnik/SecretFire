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

If Tor is not installed, SecretFire falls back to a local demo mode so you can still explore the interface.

---

## Download

Pre-built binaries are available on the [Releases](https://github.com/Xerovnik/SecretFire/releases/latest) page.

| Platform | File |
|----------|------|
| Windows  | `SecretFire-windows.exe` |
| macOS    | `SecretFire-macos` |
| Linux    | `SecretFire-linux` |

> **Note:** For full anonymity, [install Tor](https://www.torproject.org/download/) before running SecretFire. Without it, the app operates in demo mode with no network anonymity.

---

## Run from Source

**Requirements:** Python 3.10+, pip, Tor (optional but recommended)

```bash
git clone https://github.com/Xerovnik/SecretFire.git
cd SecretFire/desktop-app
pip install -r requirements.txt
python main.py
```

The app will open in your browser automatically. Your `.onion` address is displayed in the sidebar once Tor connects.

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
- No telemetry, no analytics, no crash reporting.
- Your keypair and posts are stored locally only.
- Peers know your `.onion` address but not your IP.
- Running without Tor means peers can see your IP — use Tor.

---

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE) for details.

Copyright (C) 2026 J. Zerovnik
