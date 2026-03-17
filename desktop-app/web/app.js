/* SecretFire v0.1.8 — UI script */
"use strict";

const API = "http://127.0.0.1:7474";

/* ── State ───────────────────────────────────────────────────────────── */
let appState = {
  status:      null,
  posts:       [],
  peers:       [],
  nicknames:   {},
  feedMode:    "global",
  openThreads: new Set(),
  logSince:    0,
  consoleAutoScroll: true,
  activeTab:   "feed",
};

/* ── Helpers ─────────────────────────────────────────────────────────── */
function shortKey(key) {
  if (!key) return "anon";
  return key.slice(0, 8) + "\u2026";
}

function displayName(pubkey, nick) {
  if (nick) return nick;
  if (!pubkey) return "anon";
  return pubkey.slice(0, 10) + "\u2026";
}

function fmtTime(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const diff = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diff < 60)    return "just now";
  if (diff < 3600)  return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  return d.toLocaleDateString();
}

function avatarChar(pubkey) {
  if (!pubkey) return "\uD83D\uDC7B";
  const code = pubkey.charCodeAt(0) + pubkey.charCodeAt(1);
  const pool = ["\uD83E\uDD8A","\uD83D\uDC3A","\uD83E\uDD81","\uD83D\uDC2F","\uD83E\uDD9D",
                "\uD83D\uDC38","\uD83E\uDD84","\uD83D\uDC19","\uD83D\uDC26","\uD83E\uDD9C",
                "\uD83D\uDC22","\uD83E\uDD94"];
  return pool[code % pool.length];
}

function esc(s) {
  return String(s || "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function toast(msg, type = "info") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `toast ${type} show`;
  setTimeout(() => { el.className = "toast"; }, 3200);
}

async function apiFetch(path, opts = {}) {
  const r = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${r.status}`);
  }
  return r.json();
}

/* ── Tabs ────────────────────────────────────────────────────────────── */
function showTab(name, btn) {
  ["feed","peers","console","settings"].forEach(t => {
    const el = document.getElementById(`tab-${t}`);
    if (el) el.style.display = "none";
  });
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));

  const target = document.getElementById(`tab-${name}`);
  if (target) target.style.display = (name === "console") ? "flex" : "block";
  if (btn) btn.classList.add("active");
  appState.activeTab = name;

  if (name === "peers")   renderPeersTab();
  if (name === "console") scrollConsole();
}

/* ── Status ──────────────────────────────────────────────────────────── */
async function pollStatus() {
  try {
    const data = await apiFetch("/api/status");
    appState.status = data;
    const tor = data.tor || {};

    const dot   = document.getElementById("status-dot");
    const txt   = document.getElementById("status-text");
    const badge = document.getElementById("bridge-badge");

    if (tor.demo_mode) {
      dot.className = "status-dot demo";
      txt.textContent = "Demo mode (not anonymous)";
      badge.classList.remove("visible");
    } else if (tor.connected) {
      dot.className = "status-dot " + (tor.using_bridges ? "bridges" : "online");
      txt.textContent = tor.using_bridges ? "via obfs4 bridges" : "Tor connected";
      tor.using_bridges ? badge.classList.add("visible") : badge.classList.remove("visible");
    } else {
      dot.className = "status-dot";
      txt.textContent = tor.status || "Connecting\u2026";
      badge.classList.remove("visible");
    }

    const onion = tor.onion_address || "\u2014";
    ["sidebar-onion","panel-onion","settings-onion"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = onion;
    });
    const ni = document.getElementById("settings-node-id");
    if (ni) ni.textContent = data.node_id || "\u2014";
    const vi = document.getElementById("settings-version");
    if (vi) vi.textContent = data.version ? "v" + data.version : "\u2014";

    const sp = data.stats || {};
    document.getElementById("stat-posts").textContent = sp.posts ?? "0";
    document.getElementById("stat-peers").textContent = sp.active_peers ?? "0";

    const modeEl = document.getElementById("tor-mode");
    if (modeEl) {
      modeEl.textContent = tor.demo_mode ? "Demo" : (tor.connected ? "Connected" : "Connecting");
      modeEl.className = "tor-val " + (tor.demo_mode ? "yellow" : tor.connected ? "cyan" : "");
    }
    const tp = document.getElementById("tor-transport");
    if (tp) tp.textContent = tor.using_bridges ? "obfs4" : "Direct";
    const ts = document.getElementById("tor-socks");
    if (ts) ts.textContent = tor.socks_port ? `:${tor.socks_port}` : "\u2014";
    const sb = document.getElementById("tor-sandbox");
    if (sb) {
      if (tor.demo_mode || !tor.connected) {
        sb.textContent = "\u2014";
        sb.className = "tor-val";
      } else {
        sb.textContent = tor.sandbox_enabled ? "On" : "Off";
        sb.className = "tor-val " + (tor.sandbox_enabled ? "cyan" : "yellow");
      }
    }
    const nv = document.getElementById("node-id-val");
    if (nv) nv.textContent = (data.node_id || "\u2014").slice(0,12) + "\u2026";
  } catch (_) {
    const dot = document.getElementById("status-dot");
    if (dot) dot.className = "status-dot";
    const txt = document.getElementById("status-text");
    if (txt) txt.textContent = "Server offline";
  }
}

/* ── Peers ───────────────────────────────────────────────────────────── */
async function pollPeers() {
  try {
    const [pData, nData] = await Promise.all([apiFetch("/api/peers"), apiFetch("/api/nicknames")]);
    appState.peers     = pData.peers || [];
    appState.nicknames = nData.nicknames || {};
    renderPanelPeers();
    if (appState.activeTab === "peers") renderPeersTab();
  } catch (_) {}
}

function renderPanelPeers() {
  const el = document.getElementById("panel-peer-list");
  if (!el) return;
  const active = appState.peers.filter(p => p.is_active);
  if (!active.length) {
    el.innerHTML = `<div style="color:var(--text3);font-size:12px;">No peers yet</div>`;
    return;
  }
  el.innerHTML = active.slice(0,8).map(p => {
    const nick = appState.nicknames[p.onion_address] || "";
    return `<div class="peer-item">
      <div class="peer-dot active"></div>
      ${nick ? `<span class="peer-nick">${esc(nick)}</span>` : ""}
      <span class="peer-addr" title="${esc(p.onion_address)}">${esc(p.onion_address)}</span>
    </div>`;
  }).join("");
}

function renderPeersTab() {
  const el = document.getElementById("peer-list-full");
  if (!el) return;
  if (!appState.peers.length) {
    el.innerHTML = `<div style="color:var(--text3);font-size:13px;padding:20px 0">No peers known yet.</div>`;
    return;
  }
  el.innerHTML = appState.peers.map(p => {
    const nick   = appState.nicknames[p.onion_address] || "";
    const active = p.is_active;
    const verified = p.auth_verified;
    return `<div class="peer-full-item">
      <div class="peer-dot ${active ? "active" : "inactive"}"></div>
      <div class="peer-nick-display">
        ${nick ? `<div class="peer-nick-name">${esc(nick)}</div>` : ""}
        <div class="peer-nick-addr">${esc(p.onion_address)}</div>
      </div>
      <span class="peer-status-tag ${active ? "active" : "inactive"}">${active ? "Active" : "Inactive"}</span>
      <span class="peer-status-tag" style="background:${verified ? "rgba(0,229,255,.13)" : "rgba(156,111,255,.1)"};color:${verified ? "var(--cyan)" : "var(--purple)"};" title="${verified ? "Ed25519 identity verified" : "Awaiting challenge-response"}">${verified ? "✓ Verified" : "Unverified"}</span>
      <button class="btn btn-ghost btn-sm" onclick='promptNickname("${esc(p.onion_address)}")'>Nickname</button>
    </div>`;
  }).join("");
}

async function addPeer() {
  const input = document.getElementById("new-peer-input");
  const addr  = (input.value || "").trim();
  if (!addr) return;
  try {
    await apiFetch("/api/peers", { method:"POST", body: JSON.stringify({ onion_address: addr }) });
    input.value = "";
    toast("Peer added", "success");
    await pollPeers();
  } catch (e) { toast("Failed: " + e.message, "error"); }
}

async function promptNickname(pubkey) {
  const current = appState.nicknames[pubkey] || "";
  const nick = prompt(`Nickname for ${pubkey.slice(0,14)}\u2026 (blank to remove):`, current);
  if (nick === null) return;
  try {
    await apiFetch(`/api/nicknames/${encodeURIComponent(pubkey)}`, {
      method: "PUT", body: JSON.stringify({ nickname: nick }),
    });
    toast(nick ? `Nickname set: ${nick}` : "Nickname removed", "success");
    await pollPeers();
    renderPosts();
  } catch (e) { toast("Failed: " + e.message, "error"); }
}

/* ── Feed ────────────────────────────────────────────────────────────── */
function setFeedTab(mode, btn) {
  appState.feedMode = mode;
  document.querySelectorAll(".feed-tab").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  renderPosts();
}

async function pollPosts() {
  try {
    const [pData, nData] = await Promise.all([
      apiFetch("/api/posts?limit=100"),
      apiFetch("/api/nicknames"),
    ]);
    appState.posts     = pData.posts || [];
    appState.nicknames = nData.nicknames || {};
    renderPosts();
  } catch (_) {}
}

function renderPosts() {
  const el = document.getElementById("post-list");
  if (!el) return;
  const myKey = appState.status?.public_key;
  let list = appState.posts;
  if (appState.feedMode === "local" && myKey) {
    list = list.filter(p => p.author_pubkey === myKey);
  }
  const roots = list.filter(p => !p.parent_id);
  const ctr = document.getElementById("post-count");
  if (ctr) ctr.textContent = roots.length ? `${roots.length} post${roots.length===1?"":"s"}` : "";

  if (!roots.length) {
    el.innerHTML = `<div class="empty-feed">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>
      <h3>No posts yet</h3>
      <p>${appState.feedMode === "local" ? "You haven\u2019t posted anything." : "Be the first to broadcast anonymously."}</p>
    </div>`;
    return;
  }
  el.innerHTML = roots.map(p => renderPostItem(p, myKey)).join("");
}

function renderPostItem(p, myKey) {
  const isLocal = p.author_pubkey === myKey || p.source_peer === "local";
  const nick    = appState.nicknames[p.author_pubkey] || null;
  const name    = displayName(p.author_pubkey, nick);
  const av      = avatarChar(p.author_pubkey);
  const replyCount = p.reply_count ?? 0;
  const isOpen  = appState.openThreads.has(p.id);
  const hasPub  = p.author_pubkey && p.author_pubkey !== "anon";

  const srcBadge = isLocal
    ? `<span class="post-badge badge-local">you</span>`
    : p.source_peer
      ? `<span class="post-badge badge-peer">peer</span>`
      : "";

  const nickBtn = hasPub && !nick
    ? `<button class="btn btn-ghost btn-sm" style="margin-left:auto;font-size:11px;" onclick='promptNickname("${esc(p.author_pubkey)}")'>+ nick</button>`
    : "";

  const replyLabel = replyCount
    ? `${replyCount} repl${replyCount===1?"y":"ies"}`
    : "Reply";

  const threadHtml = isOpen
    ? `<div class="thread-section" id="thread-${p.id}">
        <div id="replies-${p.id}"><div class="empty-thread">Loading\u2026</div></div>
        <div class="reply-compose">
          <textarea id="reply-ta-${p.id}" placeholder="Reply anonymously\u2026" rows="2"
            oninput="autoResize(this)"></textarea>
          <div class="reply-compose-btns">
            <button class="btn btn-primary btn-sm" onclick="submitReply('${p.id}')">Reply</button>
            <button class="btn btn-ghost btn-sm" onclick="closeThread('${p.id}')">&#10005;</button>
          </div>
        </div>
      </div>`
    : "";

  return `<div class="post-item ${isLocal?"is-local":""}" id="post-${p.id}">
    <div class="post-item-inner">
      <div class="post-header">
        <div class="post-avatar ${isLocal?"local":""}">${av}</div>
        <div class="post-meta">
          <div class="post-author">
            ${esc(name)}
            ${hasPub?`<span class="handle">${shortKey(p.author_pubkey)}</span>`:""}
            ${srcBadge}
          </div>
          <div class="post-time">${fmtTime(p.timestamp)}</div>
        </div>
        ${nickBtn}
      </div>
      <div class="post-content">${esc(p.content)}</div>
      <div class="post-actions">
        <button class="action-btn ${replyCount?"has-replies":""}" onclick="toggleThread('${p.id}')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          ${replyLabel}
        </button>
      </div>
    </div>
    ${threadHtml}
  </div>`;
}

/* ── Threads ─────────────────────────────────────────────────────────── */
async function toggleThread(postId) {
  if (appState.openThreads.has(postId)) { closeThread(postId); return; }
  appState.openThreads.add(postId);
  renderPosts();
  await loadReplies(postId);
}

function closeThread(postId) {
  appState.openThreads.delete(postId);
  renderPosts();
}

async function loadReplies(postId) {
  const el = document.getElementById(`replies-${postId}`);
  if (!el) return;
  try {
    const data    = await apiFetch(`/api/posts/${postId}/replies`);
    const replies = data.replies || [];
    const myKey   = appState.status?.public_key;
    if (!replies.length) {
      el.innerHTML = `<div class="empty-thread">No replies yet \u2014 be the first.</div>`;
      return;
    }
    el.innerHTML = replies.map(r => renderReplyItem(r, myKey)).join("");
  } catch (_) {
    el.innerHTML = `<div class="empty-thread" style="color:var(--red)">Failed to load replies.</div>`;
  }
}

function renderReplyItem(r, myKey) {
  const nick = appState.nicknames[r.author_pubkey] || null;
  const name = displayName(r.author_pubkey, nick);
  const av   = avatarChar(r.author_pubkey);
  return `<div class="reply-item">
    <div class="reply-avatar">${av}</div>
    <div class="reply-meta">
      <div class="reply-author">${esc(name)}<span class="handle">${shortKey(r.author_pubkey)}</span></div>
      <div class="reply-content">${esc(r.content)}</div>
      <div class="reply-time">${fmtTime(r.timestamp)}</div>
    </div>
  </div>`;
}

async function submitReply(parentId) {
  const ta  = document.getElementById(`reply-ta-${parentId}`);
  if (!ta) return;
  const content = ta.value.trim();
  if (!content) return;
  const btn = ta.parentElement?.querySelector(".btn-primary");
  if (btn) btn.disabled = true;
  try {
    await apiFetch("/api/posts", { method:"POST", body: JSON.stringify({ content, parent_id: parentId }) });
    ta.value = ""; ta.style.height = "";
    toast("Reply sent!", "success");
    await loadReplies(parentId);
    await pollPosts();
  } catch (e) { toast("Failed: " + e.message, "error"); }
  finally { if (btn) btn.disabled = false; }
}

/* ── Compose ─────────────────────────────────────────────────────────── */
function updateCharCount() {
  const ta  = document.getElementById("compose-input");
  const ctr = document.getElementById("char-count");
  if (!ta || !ctr) return;
  const n = ta.value.length;
  ctr.textContent = `${n} / 500`;
  ctr.className = "char-count" + (n > 500 ? " over" : n > 450 ? " warn" : "");
}

function handleComposeKey(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submitPost();
}

async function submitPost() {
  const ta  = document.getElementById("compose-input");
  const btn = document.getElementById("post-btn");
  const content = (ta.value || "").trim();
  if (!content || content.length > 500) return;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Sending`;
  try {
    await apiFetch("/api/posts", { method:"POST", body: JSON.stringify({ content }) });
    ta.value = ""; updateCharCount();
    toast("Broadcast sent!", "success");
    await pollPosts(); await pollStatus();
  } catch (e) { toast("Failed: " + e.message, "error"); }
  finally { btn.disabled = false; btn.textContent = "Broadcast"; }
}

/* ── Sync ────────────────────────────────────────────────────────────── */
async function syncNow(btn) {
  const el = btn || document.getElementById("sync-btn");
  const origHTML = el ? el.innerHTML : "";
  if (el) {
    el.disabled = true;
    el.innerHTML = `<span class="spinner"></span> Syncing\u2026`;
  }
  try {
    await apiFetch("/api/sync-now", { method:"POST" });
    toast("Sync complete \u2014 peers updated", "success");
    await pollPosts(); await pollPeers(); await pollStatus();
  } catch (e) {
    toast("Sync error: " + e.message, "error");
  } finally {
    if (el) { el.disabled = false; el.innerHTML = origHTML; }
  }
}

/* ── Identity ────────────────────────────────────────────────────────── */
async function exportIdentity() {
  toast("Opening save dialog\u2026", "info");
  try {
    const r = await apiFetch("/api/identity/export-file", { method: "POST" });
    if (r.cancelled) {
      toast("Export cancelled", "info");
    } else if (r.success) {
      toast(`Saved to: ${r.path}`, "success");
    } else {
      throw new Error(r.error || "Unknown error");
    }
  } catch (e) { toast("Export failed: " + e.message, "error"); }
}

function showImportArea() { document.getElementById("import-area-wrap").style.display = "block"; }
function hideImportArea() { document.getElementById("import-area-wrap").style.display = "none"; }

async function importIdentity() {
  const raw = (document.getElementById("import-json-input").value || "").trim();
  if (!raw) { toast("Paste your identity JSON first", "error"); return; }
  let parsed;
  try { parsed = JSON.parse(raw); } catch { toast("Invalid JSON", "error"); return; }
  if (!confirm("Importing will replace your current identity. Continue?")) return;
  try {
    const r = await apiFetch("/api/identity/import", { method:"POST", body: JSON.stringify(parsed) });
    toast(r.message || "Imported! Restart to apply.", "success");
    hideImportArea();
    document.getElementById("import-json-input").value = "";
  } catch (e) { toast("Import failed: " + e.message, "error"); }
}

/* ── Console ─────────────────────────────────────────────────────────── */
async function pollLogs() {
  try {
    const data = await apiFetch(`/api/logs?since=${appState.logSince}&limit=200`);
    const lines = data.lines || [];
    if (!lines.length) return;
    appState.logSince = lines[lines.length - 1].ts;

    const out = document.getElementById("console-output");
    if (!out) return;
    const atBottom = out.scrollHeight - out.scrollTop <= out.clientHeight + 8;

    lines.forEach(l => {
      const ts  = new Date(l.ts * 1000).toISOString().slice(11, 23);
      const div = document.createElement("div");
      div.className = "log-line";
      div.innerHTML =
        `<span class="log-ts">${ts}</span>` +
        `<span class="log-name">${esc((l.name||"").slice(0,12).padEnd(12," "))}</span>` +
        `<span class="log-msg ${l.cls||"info"}">${esc(l.msg)}</span>`;
      out.appendChild(div);
    });

    if (atBottom || appState.consoleAutoScroll) scrollConsole();
  } catch (_) {}
}

function scrollConsole() {
  const out = document.getElementById("console-output");
  if (out) out.scrollTop = out.scrollHeight;
}

function clearConsoleDisplay() {
  const out = document.getElementById("console-output");
  if (out) out.innerHTML = "";
}

/* ── Utils ───────────────────────────────────────────────────────────── */
function copyOnion() {
  const addr = document.getElementById("panel-onion")?.textContent || "";
  if (!addr || addr === "Loading\u2026" || addr === "\u2014") return;
  navigator.clipboard.writeText(addr).then(() => toast("Onion address copied", "success")).catch(() => {});
}

function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

/* ── Auto-update ─────────────────────────────────────────────────────── */
let _updateState = "idle"; // idle | downloading | ready | error

async function checkForUpdates() {
  try {
    const r = await apiFetch("/api/update/check");
    if (r && r.update_available && r.download_url) {
      const lbl = document.getElementById("update-label");
      if (lbl) lbl.textContent = `v${r.latest} available — update ready`;
      document.getElementById("update-banner").style.display = "flex";
    }
  } catch (_) { /* silent — don't bother the user if the check fails */ }
}

async function handleUpdateBtn() {
  if (_updateState === "idle") {
    await startUpdateDownload();
  } else if (_updateState === "ready") {
    await applyUpdate();
  }
}

async function startUpdateDownload() {
  const btn = document.getElementById("update-action-btn");
  const progressWrap = document.getElementById("update-progress-wrap");
  btn.disabled = true;
  btn.textContent = "Starting…";
  progressWrap.style.display = "flex";
  _updateState = "downloading";

  try {
    await apiFetch("/api/update/download", { method: "POST" });
  } catch (e) {
    toast("Update download failed to start: " + e.message, "error");
    btn.disabled = false; btn.textContent = "Download";
    _updateState = "idle";
    return;
  }

  const poll = setInterval(async () => {
    try {
      const s = await apiFetch("/api/update/progress");
      const fill = document.getElementById("update-progress-fill");
      const pct  = document.getElementById("update-progress-pct");
      const lbl  = document.getElementById("update-label");
      if (fill) fill.style.width = s.progress + "%";
      if (pct)  pct.textContent  = s.progress + "%";

      if (s.status === "ready") {
        clearInterval(poll);
        _updateState = "ready";
        if (lbl) lbl.textContent = "Update downloaded — click to apply";
        btn.disabled = false;
        btn.textContent = "Apply & Restart";
        toast("Update downloaded. Click 'Apply & Restart' when ready.", "success");
      } else if (s.status === "error") {
        clearInterval(poll);
        _updateState = "idle";
        btn.disabled = false; btn.textContent = "Retry";
        toast("Update failed: " + (s.error || "unknown error"), "error");
      }
    } catch (_) {}
  }, 600);
}

async function applyUpdate() {
  const btn = document.getElementById("update-action-btn");
  const lbl = document.getElementById("update-label");
  btn.disabled = true;
  if (lbl) lbl.textContent = "Restarting…";
  try {
    await apiFetch("/api/update/apply", { method: "POST" });
  } catch (_) { /* app exits — connection drops, that's expected */ }
}

/* ── Boot ────────────────────────────────────────────────────────────── */
async function init() {
  await pollStatus();
  await Promise.all([pollPosts(), pollPeers()]);
  setInterval(pollStatus, 5000);
  setInterval(pollPosts,  8000);
  setInterval(pollPeers,  15000);
  setInterval(pollLogs,   1500);
  pollLogs();
  // Check for updates 5 s after boot so the UI is already loaded
  setTimeout(checkForUpdates, 5000);
}

init();
