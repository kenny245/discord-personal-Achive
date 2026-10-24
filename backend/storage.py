"""Small, local-only SQLite repository for archived messages."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArchiveDB:
    def __init__(self, filename: str | Path):
        self.filename = Path(filename)
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.filename, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    id TEXT PRIMARY KEY,
                    guild_id TEXT,
                    guild_name TEXT,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'unknown',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL REFERENCES channels(id),
                    timestamp TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    attachments_json TEXT NOT NULL DEFAULT '[]',
                    pinned INTEGER,
                    source TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    imported_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_channel_time
                    ON messages(channel_id, timestamp DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_time
                    ON messages(timestamp DESC, id DESC);
                CREATE TABLE IF NOT EXISTS import_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    added INTEGER NOT NULL,
                    updated INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    scope_id TEXT,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    message_count INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                """
            )

    def import_batch(
        self,
        channels: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        source: str,
        name: str,
    ) -> dict[str, int]:
        added = updated = 0
        now = utc_now()
        # One transaction: half an import cannot be presented as complete.
        with self.connect() as db:
            for c in channels:
                channel_id = str(c.get("id") or "").strip()
                if not channel_id:
                    continue
                db.execute(
                    """INSERT INTO channels(id, guild_id, guild_name, name, kind, metadata_json)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                         guild_id=COALESCE(excluded.guild_id, channels.guild_id),
                         guild_name=COALESCE(excluded.guild_name, channels.guild_name),
                         name=CASE WHEN excluded.name=excluded.id THEN channels.name
                                   ELSE excluded.name END,
                         kind=CASE WHEN excluded.kind='unknown' THEN channels.kind
                                   ELSE excluded.kind END,
                         metadata_json=CASE WHEN excluded.metadata_json='{}'
                           THEN channels.metadata_json ELSE excluded.metadata_json END""",
                    (
                        channel_id, c.get("guild_id"), c.get("guild_name"),
                        str(c.get("name") or channel_id)[:300],
                        str(c.get("kind") or "unknown")[:30],
                        json.dumps(c.get("metadata") or {}, ensure_ascii=False),
                    ),
                )
            for m in messages:
                message_id = str(m.get("id") or "").strip()
                channel_id = str(m.get("channel_id") or "").strip()
                if not message_id.isdigit() or not 15 <= len(message_id) <= 25:
                    continue
                if not channel_id:
                    continue
                # A channel not in the original mapping is still kept, with an honest label.
                db.execute(
                    "INSERT OR IGNORE INTO channels(id, name, kind) VALUES (?, ?, 'unknown')",
                    (channel_id, channel_id),
                )
                values = (
                    message_id, channel_id, str(m.get("timestamp") or ""),
                    str(m.get("content") or ""),
                    json.dumps(m.get("attachments") or [], ensure_ascii=False),
                    None if m.get("pinned") is None else int(bool(m["pinned"])),
                    source,
                    json.dumps(m.get("metadata") or {}, ensure_ascii=False),
                    now,
                )
                existing = db.execute(
                    "SELECT channel_id FROM messages WHERE id=?", (message_id,)
                ).fetchone()
                if existing and existing["channel_id"] != channel_id:
                    raise ValueError("同一消息 ID 出现在不同频道，已拒绝导入。")
                if existing:
                    db.execute(
                        """UPDATE messages SET timestamp=?, content=?,
                             attachments_json=?, pinned=COALESCE(?, pinned),
                             source=?, metadata_json=?, imported_at=?
                             WHERE id=?""",
                        (values[2], values[3], values[4], values[5],
                         values[6], values[7], values[8], message_id),
                    )
                    updated += 1
                else:
                    db.execute(
                        """INSERT INTO messages(id, channel_id, timestamp, content,
                             attachments_json, pinned, source, metadata_json, imported_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        values,
                    )
                    added += 1
            db.execute(
                "INSERT INTO import_log(name, source, added, updated, created_at) VALUES (?, ?, ?, ?, ?)",
                (name[:250], source, added, updated, now),
            )
        return {"added": added, "updated": updated}

    def stats(self) -> dict[str, Any]:
        with self.connect() as db:
            messages = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            channels = db.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
            summaries = db.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]
            newest = db.execute(
                "SELECT name, created_at, added FROM import_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            kinds = {
                row["kind"]: row["n"]
                for row in db.execute(
                    """SELECT channels.kind, COUNT(messages.id) AS n
                       FROM channels LEFT JOIN messages ON messages.channel_id=channels.id
                       GROUP BY channels.kind"""
                )
            }
            return {
                "messages": messages, "channels": channels, "summaries": summaries,
                "kinds": kinds, "last_import": dict(newest) if newest else None,
            }

    def channels(self, search: str = "") -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT c.id, c.guild_id, c.guild_name, c.name, c.kind,
                          COUNT(m.id) AS message_count, MAX(m.timestamp) AS latest
                   FROM channels c LEFT JOIN messages m ON m.channel_id=c.id
                   WHERE c.name LIKE ? OR c.guild_name LIKE ? OR c.id LIKE ?
                   GROUP BY c.id ORDER BY message_count DESC, c.name LIMIT 1000""",
                tuple(f"%{search}%" for _ in range(3)),
            ).fetchall()
            return [dict(row) for row in rows]

    def messages(
        self, channel_id: str | None = None, query: str = "", limit: int = 40,
        offset: int = 0,
    ) -> dict[str, Any]:
        clauses = ["1=1"]
        args: list[Any] = []
        if channel_id:
            clauses.append("m.channel_id=?")
            args.append(channel_id)
        if query:
            clauses.append("(m.content LIKE ? OR m.id LIKE ? OR c.name LIKE ?)")
            args.extend([f"%{query}%"] * 3)
        where = " AND ".join(clauses)
        limit = max(1, min(100, int(limit)))
        offset = max(0, min(1_000_000, int(offset)))
        with self.connect() as db:
            total = db.execute(
                f"SELECT COUNT(*) FROM messages m JOIN channels c ON c.id=m.channel_id WHERE {where}", args
            ).fetchone()[0]
            rows = db.execute(
                f"""SELECT m.id, m.channel_id, m.timestamp, m.content,
                           m.attachments_json, m.pinned, m.source,
                           c.name AS channel_name, c.guild_name, c.guild_id, c.kind
                    FROM messages m JOIN channels c ON c.id=m.channel_id
                    WHERE {where} ORDER BY m.timestamp DESC, m.id DESC
                    LIMIT ? OFFSET ?""", [*args, limit, offset]
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["attachments"] = json.loads(item.pop("attachments_json"))
            items.append(item)
        return {"total": total, "items": items, "limit": limit, "offset": offset}

    def messages_for_summary(
        self, channel_id: str | None = None, limit: int = 20_000
    ) -> list[dict[str, Any]]:
        with self.connect() as db:
            if channel_id:
                rows = db.execute(
                    """SELECT m.id, m.timestamp, m.content, c.name AS channel_name,
                              m.attachments_json FROM messages m JOIN channels c ON c.id=m.channel_id
                       WHERE m.channel_id=? ORDER BY m.timestamp DESC, m.id DESC LIMIT ?""",
                    (channel_id, limit),
                ).fetchall()
            else:
                rows = db.execute(
                    """SELECT m.id, m.timestamp, m.content, c.name AS channel_name,
                              m.attachments_json FROM messages m JOIN channels c ON c.id=m.channel_id
                       ORDER BY m.timestamp DESC, m.id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def save_summary(
        self, title: str, scope: str, scope_id: str | None, provider: str,
        model: str, count: int, content: str, evidence: list[str],
    ) -> int:
        with self.connect() as db:
            result = db.execute(
                """INSERT INTO summaries(title, scope, scope_id, provider, model,
                   message_count, content, evidence_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (title, scope, scope_id, provider, model, count, content,
                 json.dumps(evidence, ensure_ascii=False), utc_now()),
            )
            return int(result.lastrowid)

    def summaries(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT id, title, scope, scope_id, provider, model,
                          message_count, content, evidence_json, created_at
                   FROM summaries ORDER BY id DESC LIMIT 200"""
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json"))
            result.append(item)
        return result
