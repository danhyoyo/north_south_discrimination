"""Web dashboard for one TikTok LIVE stream and standalone predictions."""

from __future__ import annotations

import json
import csv
import io
import logging
import os
from pathlib import Path
import sys
from threading import Lock

from flask import Flask, Response, jsonify, request, send_file, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virdc_stream.config import settings  # noqa: E402
from virdc_stream.database import fetch_analytics, fetch_comments  # noqa: E402
from virdc_stream.event_schema import UNCLASSIFIED_LABEL  # noqa: E402
from virdc_stream.live_schema import live_stream_id, parse_live_url  # noqa: E402

LIVE_URL = settings.tiktok_live_url or os.getenv("TIKTOK_LIVE_URL") or (
    "https://www.tiktok.com/@gronrav/live"
)
LIVE_USERNAME = parse_live_url(LIVE_URL)
STREAM_ID = live_stream_id(LIVE_USERNAME)
STATUS_PATH = ROOT / "data" / "state" / f"tiktok_live_status_{LIVE_USERNAME.lower()}.json"
app = Flask(__name__)
_manual_model = None
_manual_model_lock = Lock()


def read_history(path: Path, stream_id: str, limit: int = 500) -> tuple[list[dict], int]:
    return fetch_comments(
        path,
        video_id=stream_id,
        source="tiktok-live",
        limit=limit,
    )


@app.route("/")
def index():
    return send_file(ROOT / "web" / "overview.html")


@app.route("/live")
def live_page():
    return send_file(ROOT / "web" / "live.html")


@app.route("/analytics")
def analytics_page():
    return send_file(ROOT / "web" / "analytics.html")


@app.route("/data")
def data_page():
    return send_file(ROOT / "web" / "data.html")


@app.route("/assets/<path:filename>")
def assets(filename: str):
    return send_from_directory(ROOT / "web", filename)


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


@app.post("/api/predict")
def predict_comment():
    global _manual_model

    payload = request.get_json(silent=True)
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        return jsonify(error="Vui lòng nhập nội dung bình luận."), 400

    try:
        with _manual_model_lock:
            if _manual_model is None:
                # The dashboard can display LIVE data without loading PhoBERT.
                from virdc_stream.model_service import ModelService

                _manual_model = ModelService(settings.model_path)
            prediction = _manual_model.predict(text)
    except Exception:
        app.logger.exception("Manual comment prediction failed")
        return jsonify(error="Không thể dự đoán. Hãy kiểm tra mô hình PhoBERT trên máy chủ."), 503
    return jsonify(prediction)


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


def _comment_filters() -> dict:
    label = request.args.get("label") or None
    if label not in (None, "khác", "ủng hộ", "phân biệt", UNCLASSIFIED_LABEL):
        label = None
    try:
        min_score = float(request.args["min_score"]) if request.args.get("min_score") else None
    except ValueError:
        min_score = None
    return {
        "label": label,
        "search": request.args.get("search", "").strip() or None,
        "min_score": min_score,
    }


@app.route("/api/comments")
def comments():
    try:
        limit = min(500, max(1, int(request.args.get("limit", "50"))))
        offset = max(0, int(request.args.get("offset", "0")))
    except ValueError:
        limit, offset = 50, 0
    items, total = fetch_comments(
        settings.database_path,
        video_id=STREAM_ID,
        source="tiktok-live",
        limit=limit,
        offset=offset,
        **_comment_filters(),
    )
    return jsonify({"total": total, "limit": limit, "offset": offset, "comments": items})


@app.route("/api/analytics")
def analytics():
    result = fetch_analytics(settings.database_path, video_id=STREAM_ID, source="tiktok-live")
    return jsonify({"stream_id": STREAM_ID, "live_url": LIVE_URL, **result})


def _safe_csv(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


@app.route("/api/export.csv")
def export_csv():
    items, _ = fetch_comments(
        settings.database_path,
        video_id=STREAM_ID,
        source="tiktok-live",
        limit=10000,
        **_comment_filters(),
    )
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("comment_id", "username", "text", "label", "score", "latency_ms", "classified_at"))
    for item in items:
        prediction = item.get("prediction") or {}
        metadata = item.get("metadata") or {}
        writer.writerow((
            _safe_csv(item.get("comment_id")),
            _safe_csv(metadata.get("username") or metadata.get("unique_id")),
            _safe_csv(item.get("text")),
            _safe_csv(prediction.get("label")),
            prediction.get("score"),
            item.get("latency_ms"),
            item.get("classified_at"),
        ))
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=live-comments.csv"},
    )


@app.route("/api/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.run(host="127.0.0.1", port=8000)
