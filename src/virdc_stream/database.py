from __future__ import annotations

import json
import sqlite3
from collections import Counter
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
    label: str | None = None,
    search: str | None = None,
    min_score: float | None = None,
    limit: int = 500,
    offset: int = 0,
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
        if label is not None:
            conditions.append("label = ?")
            parameters.append(label)
        if search:
            conditions.append("(text LIKE ? COLLATE NOCASE OR username LIKE ? COLLATE NOCASE)")
            pattern = f"%{search.strip()}%"
            parameters.extend((pattern, pattern))
        if min_score is not None:
            conditions.append("score >= ?")
            parameters.append(float(min_score))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        total = int(connection.execute(
            f"SELECT COUNT(*) FROM classified_comments {where}", parameters
        ).fetchone()[0])
        rows = connection.execute(
            f"""
            SELECT payload_json FROM classified_comments
            {where}
            ORDER BY classified_at DESC
            LIMIT ? OFFSET ?
            """,
            [*parameters, max(1, int(limit)), max(0, int(offset))],
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


def fetch_analytics(
    path: str | Path,
    *,
    video_id: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
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

        summary = connection.execute(
            f"""
            SELECT COUNT(*) AS total,
                   SUM(is_discrimination) AS discrimination,
                   AVG(score) AS average_score,
                   AVG(latency_ms) AS average_latency_ms,
                   MIN(classified_at) AS first_classified_at,
                   MAX(classified_at) AS last_classified_at
            FROM classified_comments {where}
            """,
            parameters,
        ).fetchone()

        labels = [
            {"label": row["label"], "count": int(row["count"])}
            for row in connection.execute(
                f"""
                SELECT label, COUNT(*) AS count
                FROM classified_comments {where}
                GROUP BY label ORDER BY count DESC
                """,
                parameters,
            )
        ]
        hourly = [
            {"bucket": row["bucket"], "count": int(row["count"]),
             "discrimination": int(row["discrimination"] or 0)}
            for row in connection.execute(
                f"""
                SELECT substr(classified_at, 1, 13) || ':00:00Z' AS bucket,
                       COUNT(*) AS count,
                       SUM(is_discrimination) AS discrimination
                FROM classified_comments {where}
                GROUP BY bucket ORDER BY bucket DESC LIMIT 24
                """,
                parameters,
            )
        ][::-1]
        top_users = [
            {"username": row["display_name"], "count": int(row["count"]),
             "discrimination": int(row["discrimination"] or 0)}
            for row in connection.execute(
                f"""
                SELECT COALESCE(NULLIF(username, ''), 'Không rõ') AS display_name,
                       COUNT(*) AS count,
                       SUM(is_discrimination) AS discrimination
                FROM classified_comments {where}
                GROUP BY display_name ORDER BY count DESC LIMIT 10
                """,
                parameters,
            )
        ]
        confidence = [
            {"bucket": row["bucket"], "count": int(row["count"])}
            for row in connection.execute(
                f"""
                SELECT CASE
                    WHEN score < 0.5 THEN '< 50%'
                    WHEN score < 0.7 THEN '50–69%'
                    WHEN score < 0.9 THEN '70–89%'
                    ELSE '≥ 90%'
                END AS bucket,
                COUNT(*) AS count,
                MIN(score) AS ordering
                FROM classified_comments {where}
                GROUP BY bucket ORDER BY ordering
                """,
                parameters,
            )
        ]

        gift_rows = connection.execute(
            "SELECT payload_json FROM live_events WHERE stream_id = ? ORDER BY occurred_at DESC LIMIT 5000",
            (video_id,),
        ).fetchall() if video_id is not None else []
    finally:
        connection.close()

    gift_names: Counter[str] = Counter()
    gifters: set[str] = set()
    for row in gift_rows:
        try:
            event = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        name = str((event.get("gift") or {}).get("name") or "Không rõ")
        giver = str((event.get("user") or {}).get("unique_id") or "").strip()
        gift_names[name] += int((event.get("gift") or {}).get("repeat_count") or 1)
        if giver:
            gifters.add(giver)

    total = int(summary["total"] or 0)
    discrimination = int(summary["discrimination"] or 0)
    return {
        "summary": {
            "total": total,
            "discrimination": discrimination,
            "discrimination_rate": discrimination / total if total else 0.0,
            "average_score": float(summary["average_score"] or 0.0),
            "average_latency_ms": float(summary["average_latency_ms"] or 0.0),
            "first_classified_at": summary["first_classified_at"],
            "last_classified_at": summary["last_classified_at"],
        },
        "labels": labels,
        "hourly": hourly,
        "top_users": top_users,
        "confidence": confidence,
        "gifts": {
            "events": len(gift_rows),
            "unique_gifters": len(gifters),
            "top": [{"name": name, "count": count} for name, count in gift_names.most_common(8)],
        },
    }
