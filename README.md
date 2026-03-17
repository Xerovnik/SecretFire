# SecretFire

**Anonymous P2P microblogging over Tor.**

SecretFire is a decentralized, censorship-resistant messaging platform. It runs entirely on your local machine, routes all traffic through the Tor network, and communicates with peers through Tor hidden services — no central servers, no accounts, no surveillance.

---

## Features

- **No central server.** The network exists only as long as nodes are online and communicating.
- **Tor hidden services.** Your IP address is never revealed. You are identified only by your `.onion` address.
- **Ed25519 identity.** Your identity is cryptographic. A keypair is generated locally on first run and never leaves your machine, stored encrypted at rest with Argon2id + AES-256-GCM.
- **Gossip protocol.** Posts are broadcast as encrypted message fragments that propagate peer-to-peer across the network.
- **AES-256-GCM encryption.** Message content is encrypted end-to-end. Only intended recipients can reassemble fragments.
- **Signed posts.** Ed25519 signatures ensure posts genuinely originate from their claimed author.
- **Signed peer lists.** Outbound peer lists are Ed25519-signed. Inbound lists are verified before peers are accepted, preventing Sybil peer injection.
- **Challenge-response peer authentication.** Each peer must prove ownership of their Ed25519 keypair via a challenge-response handshake. Pubkey mismatches from known addresses are flagged as probable impersonation attempts.
- **Tor sandbox hardening (Linux).** Tor runs inside a seccomp syscall sandbox on Linux. If the kernel rejects it, the node automatically retries without the sandbox. `OnionTrafficOnly` blocks clearnet leaks. `IsolateDestAddr` gives each peer its own Tor circuit.
- **Bundled Tor.** SecretFire downloads the latest stable Tor binary directly from the Tor Project on first run and keeps it up to date automatically. No separate Tor installation is required.
- **Message padding.** Plaintext is padded to fixed bucket sizes before fragmentation to resist traffic analysis.

---

## Download

Pre-built binaries are available on the [Releases](https://github.com/Xerovnik/SecretFire/releases/latest) page.

| Platform | File |
|----------|------|
| Windows  | `SecretFire-windows.exe` |
| macOS    | `SecretFire-macos` (chmod +x first) |
| Linux    | `SecretFire-linux` (chmod +x first) |

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
├── tor_manager.py   — manages the embedded Tor process, sandbox fallback,
│                      IsolateDestAddr, OnionTrafficOnly
├── tor_updater.py   — downloads and verifies the Tor binary from the Tor Project
├── gossip.py        — P2P gossip loop, broadcast key rotation, signed peer lists,
│                      challenge-response integration
├── peer_auth.py     — Ed25519 challenge-response authenticator
├── protocol.py      — message padding, fragmentation, HMAC, reassembly
├── crypto_utils.py  — Ed25519 signing, AES-256-GCM encryption, HMAC-SHA256
├── identity.py      — Argon2id + AES-256-GCM encrypted identity storage
├── storage.py       — SQLite3 schema, safe migrations, CRUD helpers
├── api_server.py    — Flask REST API (localhost only)
├── config.py        — ports, paths, APP_VERSION
└── web/             — local frontend (HTML/CSS/vanilla JS)
```

---

## Cryptography

| Primitive | Algorithm | Use |
|-----------|-----------|-----|
| Signing | Ed25519 (RFC 8032) | Posts, peer lists, challenge-response |
| Encryption | AES-256-GCM | Message fragments |
| Key derivation | Argon2id (RFC 9106) | Identity file encryption |
| Integrity | HMAC-SHA256 (truncated 8B) | Per-fragment packet MAC |

### Identity storage format

```
[16 bytes]  Argon2id salt  — random, not secret
[12 bytes]  AES-GCM nonce  — random per save
[ N bytes]  AES-GCM ciphertext (JSON payload + 16-byte GCM tag)
```

Argon2id parameters: `time_cost=3`, `memory_cost=65536 KiB`, `parallelism=4`.

### Message fragment packet

```
[16 bytes]  message_id       — shared across all fragments
[ 2 bytes]  seq_num          — big-endian uint16
[ 2 bytes]  total_parts      — big-endian uint16
[ 8 bytes]  timestamp        — big-endian uint64 (Unix epoch)
[ 8 bytes]  HMAC-SHA256[:8]  — over header + encrypted payload
[ N bytes]  AES-256-GCM blob — encrypted fragment (≤ 460 bytes)
```

AAD per fragment: `msg_id (16B) ‖ seq_num (2B BE) ‖ total_parts (2B BE)` — binds ciphertext to its position, preventing reordering attacks.

---

## Peer Authentication Protocol

Challenge-response runs over two sync cycles:

**Cycle 1 — challenge issuance**
```
Node A → Node B   POST /api/sync  { from, node_pubkey }
Node B → Node A   200 OK          { ..., auth_challenge: "<32-byte nonce b64>" }
```

**Cycle 2 — response & verification**
```
Node A → Node B   POST /api/sync  { from, node_pubkey, challenge_response: "<Ed25519 sig>" }

Node B verifies:
  message = JSON.dumps({"challenge": nonce_b64, "peer": "a.onion"}, sort_keys=True)
  ed25519_verify(message, challenge_response, node_pubkey)
  → success: auth_verified = 1, pubkey locked in DB
  → failure: warning logged, peer stays Unverified
```

Once verified, a peer's public key is locked in the local database. Any future connection from the same `.onion` address using a different key is flagged as a probable impersonation attempt.

---

## Tor Security

| Feature | torrc Directive | Effect |
|---------|----------------|--------|
| Per-peer circuits | `IsolateDestAddr` | Each `.onion` peer gets its own Tor circuit |
| Clearnet blocking | `OnionTrafficOnly` | Non-onion traffic rejected at SOCKS port |
| Syscall sandbox | `Sandbox 1` (Linux) | seccomp filtering on the Tor process |
| Auto-fallback | bootstrap monitor | Retries with `Sandbox 0` if kernel rejects |

---

## Privacy Notes

- SecretFire never connects to any server outside of the Tor network.
- The Tor binary is downloaded directly from the Tor Project and verified by SHA-256 checksum before use.
- No telemetry, no analytics, no crash reporting.
- Your keypair and posts are stored locally only.
- Peers know your `.onion` address but not your IP.

---

## Changelog

| Version | Changes |
|---------|---------|
| v0.1.22 | Challenge-response peer authentication; pubkey locking; Verified/Unverified badge in UI |
| v0.1.21 | Tor sandbox auto-fallback; IsolateDestAddr; OnionTrafficOnly; sandbox status in UI |
| v0.1.20 | Fixed false "update available" banner; version bumping discipline established |
| v0.1.19 | Signed peer lists (Ed25519); broadcast key rotation; fragment rate limiting |

---

## Technical Specification

Full protocol details, wire formats, and security boundary documentation are available on the [SecretFire website](https://ghostwire-site.xerovnik.repl.co/specs).

---

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE) for details.

Copyright (C) 2026 J. Zerovnik
