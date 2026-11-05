from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS classified_comments (
    comment_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    video_id TEXT,
    source TEXT NOT NULL,
    text TEXT NOT NULL,
    username TEXT,
    label TEXT NOT NULL,
    score REAL NOT NULL,
    is_discrimination INTEGER NOT NULL,
    latency_ms REAL NOT NULL,
    ingested_at TEXT NOT NULL,
    classified_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comments_stream_time
    ON classified_comments(source, video_id, classified_at DESC);
CREATE INDEX IF NOT EXISTS idx_comments_label
    ON classified_comments(label);

CREATE TABLE IF NOT EXISTS live_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    stream_id TEXT,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_live_events_stream_time
    ON live_events(stream_id, occurred_at DESC);
"""


def connect_database(path: str | Path) -> sqlite3.Connection:
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.executescript(SCHEMA)
    return connection


def save_classified_event(connection: sqlite3.Connection, event: dict[str, Any]) -> None:
    prediction = event["prediction"]
    metadata = event.get("metadata") or {}
    connection.execute(
        """
        INSERT INTO classified_comments (
            comment_id, event_id, video_id, source, text, username, label,
            score, is_discrimination, latency_ms, ingested_at, classified_at,
            payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(comment_id) DO UPDATE SET
            event_id=excluded.event_id,
            video_id=excluded.video_id,
            source=excluded.source,
            text=excluded.text,
            username=excluded.username,
            label=excluded.label,
            score=excluded.score,
            is_discrimination=excluded.is_discrimination,
            latency_ms=excluded.latency_ms,
            ingested_at=excluded.ingested_at,
            classified_at=excluded.classified_at,
            payload_json=excluded.payload_json
        """,
        (
            str(event["comment_id"]),
            str(event["event_id"]),
            event.get("video_id"),
            str(event["source"]),
            str(event["text"]),
            metadata.get("username") or metadata.get("unique_id"),
            str(prediction["label"]),
            float(prediction["score"]),
            int(bool(prediction["is_discrimination"])),
            float(event["latency_ms"]),
            str(event["ingested_at"]),
            str(event["classified_at"]),
            json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        ),
    )
    connection.commit()


def save_live_event(path: str | Path, event: dict[str, Any]) -> None:
    connection = connect_database(path)
    try:
        connection.execute(
            """
            INSERT OR IGNORE INTO live_events (
                event_id, event_type, stream_id, occurred_at, payload_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(event["event_id"]),
                str(event["event_type"]),
                event.get("stream_id"),
                str(event["occurred_at"]),
                json.dumps(event, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def fetch_comments(
    path: str | Path,
    *,
    video_id: str | None = None,
    source: str | None = None,
    limit: int = 500,
) -> tuple[list[dict[str, Any]], int]:
    connection = connect_database(path)
    try:
        conditions: list[str] = []
        parameters: list[Any] = []
        if video_id is not None:
            conditions.append("video_id = ?")
            parameters.append(video_id)
        if source is not None:
            conditions.append("source = ?")
            parameters.append(source)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        total = int(connection.execute(
            f"SELECT COUNT(*) FROM classified_comments {where}", parameters
        ).fetchone()[0])
        rows = connection.execute(
            f"""
            SELECT payload_json FROM classified_comments
            {where}
            ORDER BY classified_at DESC
            LIMIT ?
            """,
            [*parameters, max(1, int(limit))],
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row["payload_json"]) for row in rows], total


def fetch_summary(path: str | Path) -> dict[str, Any]:
    connection = connect_database(path)
    try:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(is_discrimination) AS discrimination,
                   AVG(latency_ms) AS average_latency_ms
            FROM classified_comments
            """
        ).fetchone()
        labels = {
            item["label"]: int(item["count"])
            for item in connection.execute(
                "SELECT label, COUNT(*) AS count FROM classified_comments GROUP BY label"
            )
        }
    finally:
        connection.close()
    return {
        "total": int(row["total"] or 0),
        "discrimination": int(row["discrimination"] or 0),
        "average_latency_ms": float(row["average_latency_ms"] or 0.0),
        "labels": labels,
    }
