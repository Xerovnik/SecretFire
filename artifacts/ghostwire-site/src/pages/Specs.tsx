// SecretFire
// Copyright (C) 2026 J. Zerovnik
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

import React, { useState } from "react";
import { motion } from "framer-motion";
import { Network, ChevronRight, ArrowLeft } from "lucide-react";
import { useLocation } from "wouter";

const SECTIONS = [
  "Overview",
  "Cryptography",
  "Identity",
  "Tor Integration",
  "Gossip Protocol",
  "Peer Authentication",
  "Message Protocol",
  "Storage",
  "Architecture",
];

function SectionAnchor({ id }: { id: string }) {
  return <div id={id} className="scroll-mt-24" />;
}

function SectionTitle({ tag, children }: { tag: string; children: React.ReactNode }) {
  return (
    <h2 className="text-2xl md:text-3xl font-display text-foreground mb-6 mt-2 flex items-baseline gap-3">
      <span className="text-primary font-mono text-lg">{tag}</span>
      {children}
    </h2>
  );
}

function SubTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-lg font-display text-foreground mb-3 mt-8 border-l-2 border-primary/40 pl-4">
      {children}
    </h3>
  );
}

function Prose({ children }: { children: React.ReactNode }) {
  return <p className="text-muted-foreground leading-relaxed mb-4">{children}</p>;
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="font-mono text-sm text-primary bg-primary/10 px-1.5 py-0.5 rounded">
      {children}
    </code>
  );
}

function Block({ children, label }: { children: React.ReactNode; label?: string }) {
  return (
    <div className="my-4 rounded border border-border bg-card/60 overflow-hidden">
      {label && (
        <div className="px-4 py-1.5 text-xs font-mono text-muted-foreground border-b border-border bg-background/60">
          {label}
        </div>
      )}
      <pre className="px-4 py-4 text-sm font-mono text-foreground overflow-x-auto whitespace-pre leading-relaxed">
        {children}
      </pre>
    </div>
  );
}

function Table({ headers, rows }: { headers: string[]; rows: (string | React.ReactNode)[][] }) {
  return (
    <div className="overflow-x-auto my-4 rounded border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-background/60">
            {headers.map((h, i) => (
              <th key={i} className="px-4 py-3 text-left font-mono text-primary text-xs uppercase tracking-wider">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border/50 last:border-0 hover:bg-card/30 transition-colors">
              {row.map((cell, j) => (
                <td key={j} className="px-4 py-3 text-muted-foreground font-mono text-xs">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Tag({ children, color = "cyan" }: { children: React.ReactNode; color?: "cyan" | "purple" | "green" }) {
  const colors = {
    cyan: "bg-primary/10 border-primary/30 text-primary",
    purple: "bg-purple-500/10 border-purple-500/30 text-purple-400",
    green: "bg-green-500/10 border-green-500/30 text-green-400",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-xs font-mono border rounded ${colors[color]}`}>
      {children}
    </span>
  );
}

export default function Specs() {
  const [, navigate] = useLocation();
  const [activeSection, setActiveSection] = useState("Overview");

  const scrollTo = (id: string) => {
    setActiveSection(id);
    document.getElementById(id.toLowerCase().replace(/ /g, "-"))?.scrollIntoView({ behavior: "smooth" });
  };

  const fade = {
    initial: { opacity: 0, y: 16 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true },
    transition: { duration: 0.4 },
  };

  return (
    <div className="min-h-screen bg-background selection:bg-primary/30 selection:text-primary">
      {/* Navbar */}
      <nav className="fixed top-0 w-full z-50 bg-background/80 backdrop-blur-md border-b border-primary/20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <button
            onClick={() => navigate("/")}
            className="flex items-center gap-2 text-primary hover:text-primary/80 transition-colors"
          >
            <Network className="w-6 h-6" />
            <span className="font-display font-bold text-xl tracking-widest uppercase">SecretFire</span>
          </button>
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate("/")}
              className="hidden sm:flex items-center gap-1 text-muted-foreground hover:text-primary transition-colors font-sans text-sm uppercase tracking-wider"
            >
              <ArrowLeft className="w-4 h-4" />
              Home
            </button>
            <a
              href="https://github.com/Xerovnik/SecretFire/releases/latest"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:text-primary/80 transition-colors font-sans text-sm uppercase tracking-wider font-bold"
            >
              Download
            </a>
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 pb-24 flex gap-10">
        {/* Sidebar TOC */}
        <aside className="hidden lg:block w-52 shrink-0">
          <div className="sticky top-28">
            <p className="text-xs font-mono text-muted-foreground uppercase tracking-widest mb-4">Contents</p>
            <nav className="flex flex-col gap-1">
              {SECTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => scrollTo(s)}
                  className={`flex items-center gap-2 text-left px-3 py-1.5 text-sm rounded transition-colors ${
                    activeSection === s
                      ? "text-primary bg-primary/10"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {activeSection === s && <ChevronRight className="w-3 h-3 shrink-0" />}
                  <span className={activeSection === s ? "" : "pl-5"}>{s}</span>
                </button>
              ))}
            </nav>
          </div>
        </aside>

        {/* Content */}
        <main className="flex-1 min-w-0 max-w-3xl">
          {/* Page header */}
          <motion.div {...fade} className="mb-14">
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-primary/10 border border-primary/30 text-primary text-xs font-mono mb-5">
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
              TECHNICAL SPECIFICATION — v0.1.22
            </div>
            <h1 className="text-4xl md:text-5xl font-display font-bold text-foreground mb-4">
              System Specs
            </h1>
            <p className="text-muted-foreground text-lg max-w-2xl leading-relaxed">
              A detailed technical reference for every security-relevant component of the SecretFire
              protocol stack. All algorithms, wire formats, and design decisions are documented here.
            </p>
          </motion.div>

          {/* ── OVERVIEW ─────────────────────────────────────────────── */}
          <motion.section {...fade} className="mb-16">
            <SectionAnchor id="overview" />
            <SectionTitle tag="01">Overview</SectionTitle>
            <Prose>
              SecretFire is a fully decentralized, anonymous peer-to-peer microblogging platform.
              It routes all network traffic through the Tor onion network, uses Ed25519 cryptographic
              identities, and propagates content via an encrypted gossip protocol. There are no central
              servers, no accounts, and no IP addresses exposed — only <Code>.onion</Code> addresses.
            </Prose>
            <Prose>
              Every node runs a Tor hidden service. Nodes discover each other through signed peer
              lists and sync posts by exchanging encrypted fragments. Authentication is performed via
              Ed25519 challenge-response, preventing impersonation of known nodes.
            </Prose>
            <Table
              headers={["Component", "Technology", "Purpose"]}
              rows={[
                ["Transport", "Tor SOCKS5 + Hidden Services", "Anonymous, IP-hiding network layer"],
                ["Signing", "Ed25519", "Post integrity, peer identity, peer list signing"],
                ["Encryption", "AES-256-GCM", "Message confidentiality + authentication"],
                ["Key derivation", "Argon2id", "Identity file encryption from password"],
                ["Integrity", "HMAC-SHA256", "Per-fragment packet integrity"],
                ["Peer auth", "Ed25519 challenge-response", "Proving keypair ownership over Tor"],
                ["Storage", "SQLite 3", "Local posts, peers, fragments"],
              ]}
            />
          </motion.section>

          {/* ── CRYPTOGRAPHY ─────────────────────────────────────────── */}
          <motion.section {...fade} className="mb-16">
            <SectionAnchor id="cryptography" />
            <SectionTitle tag="02">Cryptography</SectionTitle>

            <SubTitle>Ed25519 — Signing</SubTitle>
            <Prose>
              All user-generated content and peer lists are signed with Ed25519 using the node's
              long-term keypair. The private key is generated once, encrypted with Argon2id +
              AES-256-GCM, and stored on disk. The public key doubles as the node's persistent
              identity.
            </Prose>
            <Table
              headers={["Parameter", "Value"]}
              rows={[
                ["Algorithm", "Ed25519 (RFC 8032)"],
                ["Key size", "32 bytes (256 bits)"],
                ["Signature size", "64 bytes"],
                ["Library", "cryptography (PyCA) — Ed25519PrivateKey"],
                ["Encoding", "Raw bytes → Base64 for storage / wire"],
              ]}
            />

            <SubTitle>AES-256-GCM — Message Encryption</SubTitle>
            <Prose>
              Message fragments are encrypted with AES-256-GCM using a per-session broadcast key.
              Each fragment carries additional authenticated data (AAD) that binds the ciphertext
              to its position in the message, preventing reordering or splicing attacks.
            </Prose>
            <Table
              headers={["Parameter", "Value"]}
              rows={[
                ["Algorithm", "AES-256-GCM (NIST SP 800-38D)"],
                ["Key size", "256 bits (32 bytes)"],
                ["Nonce size", "96 bits (12 bytes) — random per fragment"],
                ["Tag size", "128 bits (16 bytes)"],
                ["AAD", "msg_id (16B) ‖ seq_num (2B BE) ‖ total_parts (2B BE)"],
                ["Library", "cryptography (PyCA) — AESGCM"],
              ]}
            />

            <SubTitle>Argon2id — Identity Key Derivation</SubTitle>
            <Prose>
              The on-disk identity file is encrypted. The encryption key is derived from the user's
              password using Argon2id, tuned to approximately 0.5 s on modest desktop hardware.
            </Prose>
            <Table
              headers={["Parameter", "Value"]}
              rows={[
                ["Algorithm", "Argon2id (RFC 9106)"],
                ["Salt", "16 bytes, random per identity file"],
                ["Output length", "32 bytes (AES-256 key)"],
                ["time_cost", "3"],
                ["memory_cost", "65 536 KiB (64 MiB)"],
                ["parallelism", "4"],
                ["Library", "argon2-cffi — hash_secret_raw"],
              ]}
            />

            <SubTitle>HMAC-SHA256 — Packet Integrity</SubTitle>
            <Prose>
              Each gossip fragment packet carries a truncated HMAC-SHA256 (first 8 bytes) computed
              over the packet header and encrypted payload using the broadcast session key. This
              allows fast integrity rejection before attempting decryption.
            </Prose>
          </motion.section>

          {/* ── IDENTITY ─────────────────────────────────────────────── */}
          <motion.section {...fade} className="mb-16">
            <SectionAnchor id="identity" />
            <SectionTitle tag="03">Identity</SectionTitle>
            <Prose>
              A SecretFire identity is an Ed25519 keypair. On first run the user chooses a password;
              the private key is derived, wrapped, and written to <Code>~/.secretfire/identity.enc</Code>.
              It is decrypted once at startup and held only in memory — never written to disk in plaintext.
            </Prose>

            <SubTitle>On-Disk Format — identity.enc</SubTitle>
            <Block label="binary layout">
{`[16 bytes]  Argon2id salt        — random, not secret
[12 bytes]  AES-GCM nonce        — random per save
[ N bytes]  AES-GCM ciphertext   — JSON payload + 16-byte GCM tag`}
            </Block>
            <Prose>
              The JSON payload contains <Code>ed25519_private</Code>, <Code>ed25519_public</Code>,
              and <Code>node_id</Code> (first 16 bytes of the public key, base64-encoded).
            </Prose>

            <SubTitle>Identity Fields</SubTitle>
            <Table
              headers={["Field", "Type", "Description"]}
              rows={[
                ["node_id", "str (base64, 16B)", "Short identifier shown in UI / peer lists"],
                ["ed25519_public", "str (base64, 32B)", "Long-term verification / identity key"],
                ["ed25519_private", "str (base64, 32B)", "Signing key — held in memory only"],
              ]}
            />
          </motion.section>

          {/* ── TOR INTEGRATION ──────────────────────────────────────── */}
          <motion.section {...fade} className="mb-16">
            <SectionAnchor id="tor-integration" />
            <SectionTitle tag="04">Tor Integration</SectionTitle>
            <Prose>
              SecretFire ships without a system Tor dependency. On first run it downloads the latest
              stable Tor binary directly from the Tor Project, verifies the SHA-256 checksum, and
              persists it to <Code>~/.secretfire/</Code>. The binary is updated automatically on
              subsequent launches.
            </Prose>

            <SubTitle>SOCKS Port Configuration</SubTitle>
            <Table
              headers={["torrc Directive", "Value", "Effect"]}
              rows={[
                ["SocksPort", "9050 IsolateDestAddr", "Separate Tor circuit per peer .onion address"],
                ["SocksPort", "OnionTrafficOnly", "Clearnet traffic rejected at the SOCKS port"],
                ["HiddenServiceDir", "~/.secretfire/tor_data/hidden_service", "Persistent .onion address"],
                ["HiddenServicePort", "80 127.0.0.1:<port>", "Routes inbound onion traffic to Flask API"],
              ]}
            />

            <SubTitle>Sandbox Hardening (Linux)</SubTitle>
            <Prose>
              On Linux, Tor is started with <Code>Sandbox 1</Code> to enable seccomp-based syscall
              filtering. The bootstrap monitor watches Tor's output for sandbox rejection patterns.
              If the kernel rejects seccomp (older kernels or restrictive containers), the node
              automatically retries with <Code>Sandbox 0</Code> and logs a warning. The UI shows
              the current sandbox state in the Tor Status panel.
            </Prose>
            <Table
              headers={["Platform", "Default sandbox state"]}
              rows={[
                ["Linux (modern kernel)", "On — seccomp syscall filtering active"],
                ["Linux (legacy/container)", "Off — auto-downgraded after rejection detected"],
                ["macOS / Windows", "Off — not applicable"],
              ]}
            />

            <SubTitle>Circuit Isolation</SubTitle>
            <Prose>
              <Code>IsolateDestAddr</Code> ensures that each distinct <Code>.onion</Code> peer
              address uses a separate Tor circuit. This prevents a malicious exit (irrelevant for
              onion-only traffic) or a compromised relay from correlating traffic between different
              peers by observing the same circuit carrying multiple destinations.
            </Prose>
            <Prose>
              <Code>OnionTrafficOnly</Code> blocks any non-onion traffic from exiting through the
              SecretFire SOCKS port. Since every peer connection targets a <Code>.onion</Code> address,
              this is a hard constraint that prevents accidental clearnet leaks if a peer address is
              ever malformed or substituted.
            </Prose>
          </motion.section>

          {/* ── GOSSIP PROTOCOL ──────────────────────────────────────── */}
          <motion.section {...fade} className="mb-16">
            <SectionAnchor id="gossip-protocol" />
            <SectionTitle tag="05">Gossip Protocol</SectionTitle>
            <Prose>
              Nodes maintain a list of known peers. Every <Code>GOSSIP_INTERVAL</Code> seconds
              (default 30 s), the gossip loop contacts all active peers via HTTP POST to
              <Code>/api/sync</Code> over Tor SOCKS. Every fifth cycle, inactive peers are also
              included for reconnection attempts.
            </Prose>

            <SubTitle>Sync Request Fields</SubTitle>
            <Block label="POST /api/sync — request body">
{`{
  "from":               "<caller's .onion address>",
  "known_post_ids":     ["<post_id>", ...],
  "broadcast_key":      "<base64 AES-256 key>",
  "key_id":             "<8-char key identifier>",
  "node_pubkey":        "<base64 Ed25519 public key>",
  "challenge_response": "<base64 Ed25519 signature>"  // optional
}`}
            </Block>

            <SubTitle>Sync Response Fields</SubTitle>
            <Block label="POST /api/sync — response body">
{`{
  "posts":          [{ "post_id", "content", "author_pubkey",
                        "signature", "timestamp", "parent_id" }, ...],
  "peers":          ["<onion_address>", ...],
  "peer_signature": {
    "peers":     [...],
    "timestamp": <unix>,
    "nonce":     "<base64>",
    "signer":    "<base64 pubkey>",
    "signature": "<base64 Ed25519 sig>"
  },
  "key_id":         "<current broadcast key id>",
  "auth_challenge": "<base64 32-byte nonce>"   // included when node_pubkey present
}`}
            </Block>

            <SubTitle>Signed Peer Lists</SubTitle>
            <Prose>
              Outbound peer lists are signed with the node's Ed25519 private key before transmission.
              The signed envelope includes a timestamp and random nonce to prevent replay. Receivers
              reject envelopes older than 5 minutes. This prevents Sybil peer injection — an attacker
              cannot forge a peer list signed by a key they don't control.
            </Prose>

            <SubTitle>Broadcast Key Rotation</SubTitle>
            <Prose>
              A fresh AES-256 broadcast key is generated at startup and rotated every 24 hours.
              Up to three previous keys are retained briefly to decrypt fragments from nodes
              that haven't yet synced the new key. Each key is tagged with an 8-character
              <Code>key_id</Code> included in all packets.
            </Prose>
          </motion.section>

          {/* ── PEER AUTHENTICATION ──────────────────────────────────── */}
          <motion.section {...fade} className="mb-16">
            <SectionAnchor id="peer-authentication" />
            <SectionTitle tag="06">Peer Authentication</SectionTitle>
            <Prose>
              The challenge-response protocol proves that a connecting node actually holds the
              Ed25519 private key matching the public key it advertises. Without this, an attacker
              who observes a node's pubkey could impersonate it by claiming the same identity.
            </Prose>

            <SubTitle>Handshake Flow (two sync cycles)</SubTitle>
            <Block label="cycle 1 — challenge issuance">
{`Node A  →  Node B   POST /api/sync
                      { from: "a.onion", node_pubkey: "<pubA>" }

Node B  →  Node A   200 OK
                      { ..., auth_challenge: "<base64 nonce 32B>" }`}
            </Block>
            <Block label="cycle 2 — response & verification">
{`Node A  →  Node B   POST /api/sync
                      { from: "a.onion", node_pubkey: "<pubA>",
                        challenge_response: "<Ed25519 sig>" }

Node B verifies:
  message = JSON.dumps({"challenge": nonce_b64, "peer": "a.onion"}, sort_keys=True)
  verify_ed25519(message, challenge_response, pubA)

  → success: peers.auth_verified = 1, auth_pubkey locked in DB
  → failure: warning logged, peer remains Unverified`}
            </Block>

            <SubTitle>Challenge Message Format</SubTitle>
            <Prose>
              The signed message is a deterministic JSON string. Binding the responder's onion
              address into the message prevents a challenge issued for one context from being
              replayed in another.
            </Prose>
            <Block label="message signed by the challenged node">
{`JSON.dumps(
  {"challenge": "<base64 nonce>", "peer": "<responder .onion>"},
  sort_keys=True
)`}
            </Block>

            <SubTitle>Pubkey Locking</SubTitle>
            <Prose>
              Once a peer's pubkey is verified, it is stored in the local database as
              <Code>auth_pubkey</Code>. Any future connection from the same <Code>.onion</Code> address
              using a different pubkey is immediately flagged as a probable impersonation attempt and
              logged as a warning. The verification state is visible in the Peers tab.
            </Prose>

            <Table
              headers={["State", "Color", "Meaning"]}
              rows={[
                [<Tag color="cyan">✓ Verified</Tag>, "cyan", "Ed25519 challenge-response passed; pubkey locked"],
                [<Tag color="purple">Unverified</Tag>, "purple", "Peer connected but hasn't completed handshake yet"],
              ]}
            />

            <SubTitle>Challenge Parameters</SubTitle>
            <Table
              headers={["Parameter", "Value"]}
              rows={[
                ["Nonce size", "32 bytes (256 bits) — OS random"],
                ["Challenge TTL", "300 seconds (5 minutes)"],
                ["Signing algorithm", "Ed25519"],
                ["Persistence", "Challenges in-memory (GossipManager); pubkey in SQLite"],
                ["Backward compatibility", "Peers without node_pubkey field continue to sync as Unverified"],
              ]}
            />
          </motion.section>

          {/* ── MESSAGE PROTOCOL ─────────────────────────────────────── */}
          <motion.section {...fade} className="mb-16">
            <SectionAnchor id="message-protocol" />
            <SectionTitle tag="07">Message Protocol</SectionTitle>
            <Prose>
              Long messages are split into fixed-size encrypted fragments that are broadcast
              individually. This makes traffic analysis harder — an observer sees many small packets
              of similar size rather than a single large payload that reveals message length.
            </Prose>

            <SubTitle>Packet Wire Format</SubTitle>
            <Block label="binary packet layout (per fragment)">
{`[16 bytes]  message_id          — random, shared across all fragments of a message
[ 2 bytes]  seq_num             — fragment index (big-endian uint16)
[ 2 bytes]  total_parts         — total fragment count (big-endian uint16)
[ 8 bytes]  timestamp           — Unix epoch (big-endian uint64)
[ 8 bytes]  HMAC-SHA256[:8]     — truncated MAC over header + payload
[ N bytes]  AES-256-GCM blob    — encrypted fragment chunk (≤ 460 bytes)`}
            </Block>

            <SubTitle>Message-Level Padding</SubTitle>
            <Prose>
              Before fragmentation the plaintext is padded with random bytes to the next fixed
              bucket size. The original length is stored in the last 2 bytes so it can be recovered
              exactly after reassembly. This prevents size-based content fingerprinting.
            </Prose>
            <Table
              headers={["Bucket (bytes)", "Messages that fit"]}
              rows={[
                ["256", "Up to 254 bytes of plaintext"],
                ["512", "255 – 510 bytes"],
                ["1024", "511 – 1022 bytes"],
                ["2048", "1023 – 2046 bytes"],
                ["4096", "2047 – 4094 bytes"],
                ["> 4096", "Padded with 2-byte zero sentinel only"],
              ]}
            />

            <SubTitle>Anti-Replay &amp; Rate Limiting</SubTitle>
            <Prose>
              Fragments with a timestamp older than 48 hours or more than 5 minutes in the future
              are rejected. A sliding-window rate limiter allows at most 120 fragments per 60 seconds
              per node, protecting against fragment floods. Fragment payloads larger than 8 192 bytes
              are rejected before parsing.
            </Prose>
          </motion.section>

          {/* ── STORAGE ──────────────────────────────────────────────── */}
          <motion.section {...fade} className="mb-16">
            <SectionAnchor id="storage" />
            <SectionTitle tag="08">Storage</SectionTitle>
            <Prose>
              All persistent data is stored in a single SQLite database at
              <Code>~/.secretfire/node.db</Code>. The schema is versioned through safe
              <Code>ALTER TABLE</Code> migrations that run on every startup — existing databases
              are upgraded automatically without data loss.
            </Prose>

            <SubTitle>Schema</SubTitle>
            <Block label="posts table">
{`id           TEXT PRIMARY KEY    — UUID post identifier
content      TEXT NOT NULL       — plaintext post body
author_pubkey TEXT               — Ed25519 public key (base64)
signature    TEXT                — Ed25519 signature over content (base64)
timestamp    INTEGER NOT NULL    — Unix epoch (author's clock)
received_at  INTEGER NOT NULL    — Unix epoch (local receipt time)
source_peer  TEXT                — .onion address that delivered this post
parent_id    TEXT                — parent post_id for replies`}
            </Block>
            <Block label="peers table">
{`onion_address TEXT PRIMARY KEY  — v3 .onion address (56 chars + .onion)
first_seen    INTEGER NOT NULL   — Unix epoch
last_seen     INTEGER NOT NULL   — Unix epoch
is_active     INTEGER DEFAULT 1  — 0 = inactive / unreachable
posts_shared  INTEGER DEFAULT 0  — count of posts relayed (informational)
auth_pubkey   TEXT               — claimed Ed25519 public key
auth_verified INTEGER DEFAULT 0  — 1 = challenge-response passed`}
            </Block>
            <Block label="fragments table">
{`id             INTEGER PK AUTOINCREMENT
message_id     TEXT NOT NULL     — base64 message_id
seq_num        INTEGER NOT NULL  — fragment index
total_parts    INTEGER NOT NULL  — expected fragment count
encrypted_blob BLOB NOT NULL     — raw AES-GCM ciphertext
session_key    BLOB              — base64 broadcast key used for this message
received_at    INTEGER NOT NULL
UNIQUE(message_id, seq_num)`}
            </Block>
            <Block label="nicknames table">
{`pubkey    TEXT PRIMARY KEY  — Ed25519 public key
nickname  TEXT NOT NULL     — user-assigned display name
created_at INTEGER NOT NULL`}
            </Block>
          </motion.section>

          {/* ── ARCHITECTURE ─────────────────────────────────────────── */}
          <motion.section {...fade} className="mb-8">
            <SectionAnchor id="architecture" />
            <SectionTitle tag="09">Architecture</SectionTitle>
            <Prose>
              The desktop application is a single Python process. The UI runs locally in a
              bundled WebKit window (or the default browser on Linux). The Flask API server
              listens on localhost only — it is never directly reachable over Tor. Inbound onion
              traffic is routed by Tor to the API server via the hidden service port mapping.
            </Prose>
            <Block label="desktop-app/ — module map">
{`main.py          — startup orchestration, Tor + gossip + API server lifecycle
tor_manager.py   — Tor process management, sandbox fallback, SOCKS proxies
tor_updater.py   — downloads and verifies the Tor binary from torproject.org
gossip.py        — P2P sync loop, key rotation, signed peer lists, auth integration
peer_auth.py     — Ed25519 challenge-response authenticator
protocol.py      — message padding, fragmentation, HMAC, reassembly
crypto_utils.py  — Ed25519, AES-256-GCM, HMAC-SHA256 primitives
identity.py      — Argon2id + AES-GCM encrypted identity storage
storage.py       — SQLite3 schema, migrations, CRUD helpers
api_server.py    — Flask REST API (local only)
config.py        — ports, paths, APP_VERSION
web/             — local frontend (HTML / CSS / vanilla JS)`}
            </Block>

            <SubTitle>Data Flow</SubTitle>
            <Block label="post broadcast path">
{`User writes post
  → api_server.py   signs with Ed25519, saves to posts table
  → gossip.py       pads + fragments, encrypts with broadcast key
                    broadcasts each fragment packet to all active peers

Peer receives fragment
  → api_server.py   routes to gossip.receive_fragment()
  → gossip.py       validates HMAC, checks timestamp, rate-limits
                    stores fragment in SQLite
                    on complete set → reassembles → decrypts → saves post`}
            </Block>

            <SubTitle>Security Boundaries</SubTitle>
            <Table
              headers={["Boundary", "Protection"]}
              rows={[
                ["IP address", "Tor hidden services — never exposed"],
                ["Identity on disk", "Argon2id + AES-256-GCM — encrypted at rest"],
                ["Message content", "AES-256-GCM per fragment — encrypted in transit"],
                ["Post authorship", "Ed25519 signatures — forgery-resistant"],
                ["Peer lists", "Ed25519-signed envelopes — Sybil-resistant"],
                ["Peer identity", "Ed25519 challenge-response — impersonation-resistant"],
                ["Tor process", "seccomp sandbox (Linux) — syscall-filtered"],
                ["Clearnet leaks", "OnionTrafficOnly SOCKS port — hard blocked"],
                ["Circuit correlation", "IsolateDestAddr — one circuit per peer"],
              ]}
            />
          </motion.section>

          <div className="border-t border-border pt-8 text-center">
            <p className="text-muted-foreground font-mono text-xs">
              SECRETFIRE v0.1.22 // TECHNICAL SPECIFICATION // GPLv3
            </p>
            <p className="text-muted-foreground/50 text-xs mt-1">
              Copyright (C) 2026 J. Zerovnik
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}
