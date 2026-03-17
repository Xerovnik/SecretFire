# SecretFire
# Copyright (C) 2026 J. Zerovnik
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sqlite3
import json
import threading
from datetime import datetime
from config import DB_PATH, DATA_DIR

_local = threading.local()


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            author_pubkey TEXT,
            signature TEXT,
            timestamp INTEGER NOT NULL,
            received_at INTEGER NOT NULL,
            source_peer TEXT,
            parent_id TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS fragments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT NOT NULL,
            seq_num INTEGER NOT NULL,
            total_parts INTEGER NOT NULL,
            encrypted_blob BLOB NOT NULL,
            session_key BLOB,
            received_at INTEGER NOT NULL,
            UNIQUE(message_id, seq_num)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS peers (
            onion_address TEXT PRIMARY KEY,
            first_seen INTEGER NOT NULL,
            last_seen INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1,
            posts_shared INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS key_store (
            key_id TEXT PRIMARY KEY,
            key_type TEXT NOT NULL,
            key_data TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS nicknames (
            pubkey TEXT PRIMARY KEY,
            nickname TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    _migrate()


def _migrate():
    """Safe migrations for existing databases — adds columns if missing."""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    existing_posts = {row[1] for row in c.execute("PRAGMA table_info(posts)").fetchall()}
    if "parent_id" not in existing_posts:
        c.execute("ALTER TABLE posts ADD COLUMN parent_id TEXT")

    conn.commit()
    conn.close()


def _conn():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn


def _now():
    return int(datetime.now().timestamp())


def save_post(post_id, content, author_pubkey=None, signature=None,
              timestamp=None, source_peer=None, parent_id=None):
    conn = _conn()
    ts = timestamp if timestamp else _now()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO posts "
            "(id, content, author_pubkey, signature, timestamp, received_at, source_peer, parent_id) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (post_id, content, author_pubkey, signature, ts, _now(), source_peer, parent_id),
        )
        conn.commit()
        return True
    except Exception:
        return False


def get_posts(limit=100, offset=0, root_only=False):
    q = ("SELECT id, content, author_pubkey, timestamp, received_at, source_peer, parent_id "
         "FROM posts")
    if root_only:
        q += " WHERE parent_id IS NULL"
    q += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    rows = _conn().execute(q, (limit, offset)).fetchall()
    return [dict(r) for r in rows]


def get_replies(parent_id: str) -> list[dict]:
    rows = _conn().execute(
        "SELECT id, content, author_pubkey, timestamp, received_at, source_peer, parent_id "
        "FROM posts WHERE parent_id=? ORDER BY timestamp ASC",
        (parent_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_reply_counts(post_ids: list[str]) -> dict[str, int]:
    if not post_ids:
        return {}
    placeholders = ",".join("?" * len(post_ids))
    rows = _conn().execute(
        f"SELECT parent_id, COUNT(*) FROM posts WHERE parent_id IN ({placeholders}) GROUP BY parent_id",
        post_ids,
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def get_post_ids():
    rows = _conn().execute("SELECT id FROM posts").fetchall()
    return [r[0] for r in rows]


def post_exists(post_id):
    row = _conn().execute("SELECT 1 FROM posts WHERE id=?", (post_id,)).fetchone()
    return row is not None


def save_peer(onion_address):
    conn = _conn()
    now = _now()
    conn.execute(
        "INSERT INTO peers (onion_address, first_seen, last_seen, is_active) VALUES (?,?,?,1) "
        "ON CONFLICT(onion_address) DO UPDATE SET last_seen=excluded.last_seen, is_active=1",
        (onion_address, now, now),
    )
    conn.commit()


def get_peers(active_only=False):
    q = "SELECT onion_address, last_seen, is_active, posts_shared FROM peers"
    if active_only:
        q += " WHERE is_active=1"
    q += " ORDER BY last_seen DESC"
    rows = _conn().execute(q).fetchall()
    return [dict(r) for r in rows]


def update_peer_status(onion_address, is_active):
    conn = _conn()
    conn.execute(
        "UPDATE peers SET is_active=?, last_seen=? WHERE onion_address=?",
        (1 if is_active else 0, _now(), onion_address),
    )
    conn.commit()


def set_nickname(pubkey: str, nickname: str):
    conn = _conn()
    conn.execute(
        "INSERT INTO nicknames (pubkey, nickname, created_at) VALUES (?,?,?) "
        "ON CONFLICT(pubkey) DO UPDATE SET nickname=excluded.nickname",
        (pubkey, nickname.strip(), _now()),
    )
    conn.commit()


def delete_nickname(pubkey: str):
    conn = _conn()
    conn.execute("DELETE FROM nicknames WHERE pubkey=?", (pubkey,))
    conn.commit()


def get_nicknames() -> dict[str, str]:
    rows = _conn().execute("SELECT pubkey, nickname FROM nicknames").fetchall()
    return {r[0]: r[1] for r in rows}


def save_fragment(message_id, seq_num, total_parts, encrypted_blob, session_key=None):
    conn = _conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO fragments "
            "(message_id, seq_num, total_parts, encrypted_blob, session_key, received_at) "
            "VALUES (?,?,?,?,?,?)",
            (message_id, seq_num, total_parts, encrypted_blob, session_key, _now()),
        )
        conn.commit()
        return True
    except Exception:
        return False


def get_fragments(message_id):
    rows = _conn().execute(
        "SELECT seq_num, total_parts, encrypted_blob, session_key "
        "FROM fragments WHERE message_id=? ORDER BY seq_num",
        (message_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_complete_message_ids():
    rows = _conn().execute("""
        SELECT message_id, COUNT(*) as got, MAX(total_parts) as total
        FROM fragments
        GROUP BY message_id
        HAVING got >= total
    """).fetchall()
    return [r[0] for r in rows]


def delete_fragments(message_id):
    conn = _conn()
    conn.execute("DELETE FROM fragments WHERE message_id=?", (message_id,))
    conn.commit()


def save_key(key_id, key_type, key_data):
    conn = _conn()
    conn.execute(
        "INSERT OR IGNORE INTO key_store (key_id, key_type, key_data, created_at) VALUES (?,?,?,?)",
        (key_id, key_type, json.dumps(key_data) if not isinstance(key_data, str) else key_data, _now()),
    )
    conn.commit()


def get_key(key_id):
    row = _conn().execute("SELECT key_data FROM key_store WHERE key_id=?", (key_id,)).fetchone()
    if row:
        try:
            return json.loads(row[0])
        except Exception:
            return row[0]
    return None


def get_stats():
    conn = _conn()
    post_count = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    peer_count = conn.execute("SELECT COUNT(*) FROM peers WHERE is_active=1").fetchone()[0]
    fragment_count = conn.execute("SELECT COUNT(DISTINCT message_id) FROM fragments").fetchone()[0]
    return {"posts": post_count, "active_peers": peer_count, "pending_fragments": fragment_count}
