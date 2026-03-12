const API = "";
let allPosts = [];
let feedTab = "global";
let myPubKey = "";
let refreshInterval = null;

async function apiFetch(path, opts = {}) {
  const r = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function loadStatus() {
  try {
    const data = await apiFetch("/api/status");
    myPubKey = data.public_key || "";

    const dot = document.getElementById("status-dot");
    const txt = document.getElementById("status-text");
    const onion = data.tor?.onion_address || "unknown";

    if (data.tor?.demo_mode) {
      dot.className = "status-dot demo";
      txt.textContent = "Demo Mode (no Tor)";
      document.getElementById("tor-mode").textContent = "DEMO";
      document.getElementById("tor-mode").className = "tor-val yellow";
    } else if (data.tor?.running) {
      dot.className = "status-dot online";
      txt.textContent = "Tor Active";
      document.getElementById("tor-mode").textContent = "Tor";
      document.getElementById("tor-mode").className = "tor-val green";
    } else {
      dot.className = "status-dot";
      txt.textContent = "Tor Offline";
      document.getElementById("tor-mode").textContent = "Offline";
      document.getElementById("tor-mode").className = "tor-val red";
    }

    const socks = data.tor?.socks_port;
    document.getElementById("tor-socks").textContent = socks ? `127.0.0.1:${socks}` : "N/A";

    const shortId = (data.node_id || "").slice(0, 12);
    document.getElementById("node-id-val").textContent = shortId || "—";

    document.getElementById("sidebar-onion").textContent = onion;
    document.getElementById("panel-onion").textContent = onion;

    const stats = data.stats || {};
    document.getElementById("stat-posts").textContent = stats.posts ?? 0;
    document.getElementById("stat-peers").textContent = stats.active_peers ?? 0;
  } catch (e) {
    console.error("Status load failed:", e);
  }
}

async function loadPosts() {
  try {
    const data = await apiFetch("/api/posts?limit=100");
    allPosts = data.posts || [];
    renderPosts();
    document.getElementById("post-count").textContent = `${allPosts.length} post${allPosts.length !== 1 ? "s" : ""}`;
  } catch (e) {
    console.error("Posts load failed:", e);
  }
}

function renderPosts() {
  const list = document.getElementById("post-list");
  let posts = allPosts;

  if (feedTab === "local") {
    posts = posts.filter(p => p.author_pubkey === myPubKey);
  }

  if (!posts.length) {
    list.innerHTML = `
      <div class="empty-feed">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
        <h3>${feedTab === "local" ? "No posts from you yet" : "No posts yet"}</h3>
        <p>${feedTab === "local" ? "Write something above to broadcast it." : "Be the first to broadcast anonymously."}</p>
      </div>`;
    return;
  }

  list.innerHTML = posts.map(post => renderPostItem(post)).join("");
}

function renderPostItem(post) {
  const isLocal = post.author_pubkey === myPubKey;
  const ts = new Date(post.timestamp * 1000);
  const timeStr = formatTime(ts);
  const shortKey = post.author_pubkey ? escapeHtml(shortPubKey(post.author_pubkey)) : "anon";
  const avatarEmoji = isLocal ? "👻" : getAvatar(post.author_pubkey);

  return `
    <div class="post-item">
      <div class="post-header">
        <div class="post-avatar ${isLocal ? "local" : ""}">${avatarEmoji}</div>
        <div class="post-meta">
          <div class="post-author">
            ${isLocal ? "You" : "Anonymous"}
            <span>${shortKey}</span>
          </div>
          <div class="post-time">${timeStr}</div>
        </div>
        <span class="post-badge ${isLocal ? "badge-local" : "badge-peer"}">
          ${isLocal ? "local" : post.source_peer === "fragment-reassembly" ? "📦 fragmented" : "📡 peer"}
        </span>
      </div>
      <div class="post-content">${escapeHtml(post.content)}</div>
    </div>`;
}

function getAvatar(pubkey) {
  if (!pubkey) return "👤";
  const emojis = ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘","⭐","🌟","💫","✨","🔮","🌀","🌊","⚡","🔥","❄️","🌿","🍃"];
  let hash = 0;
  for (let i = 0; i < pubkey.length; i++) hash = (hash * 31 + pubkey.charCodeAt(i)) >>> 0;
  return emojis[hash % emojis.length];
}

function shortPubKey(pubkey) {
  if (!pubkey) return "anon";
  return pubkey.slice(0, 8) + "…";
}

function escapeHtml(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function formatTime(date) {
  const now = new Date();
  const diff = (now - date) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

async function submitPost() {
  const input = document.getElementById("compose-input");
  const btn = document.getElementById("post-btn");
  const content = input.value.trim();

  if (!content) return;
  if (content.length > 500) { showToast("Post too long (max 500 chars)", "error"); return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';

  try {
    await apiFetch("/api/posts", {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    input.value = "";
    updateCharCount();
    showToast("Broadcast sent 📡", "success");
    await loadPosts();
    await loadStatus();
  } catch (e) {
    showToast("Failed to post: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = "Broadcast";
  }
}

function handleComposeKey(e) {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    submitPost();
  }
}

function updateCharCount() {
  const input = document.getElementById("compose-input");
  const count = input.value.length;
  const el = document.getElementById("char-count");
  el.textContent = `${count} / 500`;
  el.className = "char-count" + (count > 450 ? (count > 500 ? " over" : " warn") : "");
}

async function loadPeers() {
  try {
    const data = await apiFetch("/api/peers");
    const peers = data.peers || [];
    renderPanelPeers(peers);
    renderFullPeerList(peers);
  } catch (e) {
    console.error("Peers load failed:", e);
  }
}

function renderPanelPeers(peers) {
  const el = document.getElementById("panel-peer-list");
  const active = peers.filter(p => p.is_active);
  if (!active.length) {
    el.innerHTML = `<div style="color:var(--text2);font-size:13px;">No active peers</div>`;
    return;
  }
  el.innerHTML = active.slice(0, 8).map(p => `
    <div class="peer-item">
      <div class="peer-dot active"></div>
      <div class="peer-addr">${escapeHtml(p.onion_address)}</div>
    </div>`).join("");
}

function renderFullPeerList(peers) {
  const el = document.getElementById("peer-list-full");
  if (!peers.length) {
    el.innerHTML = `<p style="color:var(--text2);font-size:13px;">No peers known yet. Add one below or wait for bootstrap.</p>`;
    return;
  }
  el.innerHTML = `
    <div style="background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;">
      ${peers.map(p => `
        <div class="peer-item" style="padding:10px 14px;">
          <div class="peer-dot ${p.is_active ? "active" : "inactive"}"></div>
          <div class="peer-addr" style="font-size:12px;">${escapeHtml(p.onion_address)}</div>
          <span style="font-size:11px;color:var(--text2);">${p.is_active ? "active" : "inactive"}</span>
        </div>`).join("")}
    </div>`;
}

async function addPeer() {
  const input = document.getElementById("new-peer-input");
  const addr = input.value.trim();
  if (!addr) return;
  try {
    await apiFetch("/api/peers", {
      method: "POST",
      body: JSON.stringify({ onion_address: addr }),
    });
    input.value = "";
    showToast("Peer added", "success");
    await loadPeers();
  } catch (e) {
    showToast("Failed to add peer", "error");
  }
}

async function syncNow() {
  showToast("Syncing with peers…", "success");
  try {
    const data = await apiFetch("/api/sync-now", { method: "POST" });
    await loadPosts();
    await loadStatus();
    await loadPeers();
    showToast(`Sync complete. ${data.stats?.posts ?? "?"} posts stored.`, "success");
  } catch (e) {
    showToast("Sync failed: " + e.message, "error");
  }
}

function showTab(tab, el) {
  document.getElementById("tab-feed").style.display = tab === "feed" ? "" : "none";
  document.getElementById("tab-peers").style.display = tab === "peers" ? "" : "none";
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
  el.classList.add("active");
  if (tab === "peers") loadPeers();
}

function setFeedTab(tab, el) {
  feedTab = tab;
  document.querySelectorAll(".feed-tab").forEach(b => b.classList.remove("active"));
  el.classList.add("active");
  renderPosts();
}

function copyOnion() {
  const addr = document.getElementById("panel-onion").textContent;
  navigator.clipboard.writeText(addr).then(() => showToast("Copied .onion address", "success"));
}

let toastTimer;
function showToast(msg, type = "success") {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.className = `toast ${type} show`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.className = "toast"; }, 3000);
}

async function init() {
  await loadStatus();
  await loadPosts();
  await loadPeers();

  refreshInterval = setInterval(async () => {
    await loadStatus();
    await loadPosts();
    await loadPeers();
  }, 15000);
}

init();
