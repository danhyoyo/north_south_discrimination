"""Small read-only web dashboard for one TikTok LIVE stream."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys

from flask import Flask, jsonify, request, send_file

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virdc_stream.config import settings  # noqa: E402
from virdc_stream.database import fetch_comments  # noqa: E402
from virdc_stream.live_schema import live_stream_id, parse_live_url  # noqa: E402

LIVE_URL = settings.tiktok_live_url or os.getenv("TIKTOK_LIVE_URL") or (
    "https://www.tiktok.com/@gronrav/live"
)
LIVE_USERNAME = parse_live_url(LIVE_URL)
STREAM_ID = live_stream_id(LIVE_USERNAME)
STATUS_PATH = ROOT / "data" / "state" / f"tiktok_live_status_{LIVE_USERNAME.lower()}.json"
app = Flask(__name__)


def read_history(path: Path, stream_id: str, limit: int = 500) -> tuple[list[dict], int]:
    return fetch_comments(
        path,
        video_id=stream_id,
        source="tiktok-live",
        limit=limit,
    )


@app.route("/")
def index():
    return send_file(ROOT / "web" / "live.html")


@app.route("/api/snapshot")
def snapshot():
    try:
        limit = min(1000, max(1, int(request.args.get("limit", "200"))))
    except ValueError:
        limit = 200
    items, total = read_history(settings.database_path, STREAM_ID, limit)
    try:
        status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        status = {"state": "waiting", "checked_at": None, "visible_comments": 0,
                  "new_comments": 0}
    return jsonify({"video_id": STREAM_ID, "stream_id": STREAM_ID, "live_url": LIVE_URL,
                    "video_url": LIVE_URL, "unique_id": LIVE_USERNAME,
                    "poll_interval_seconds": status.get("interval_seconds", 5), "status": status,
                    "total": total, "comments": items})


@app.route("/api/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.run(host="127.0.0.1", port=8000)
