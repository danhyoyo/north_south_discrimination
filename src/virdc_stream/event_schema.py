from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


RAW_REQUIRED_FIELDS = ("event_id", "comment_id", "text", "source", "ingested_at")
UNCLASSIFIED_LABEL = "chưa phân loại"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_raw_event(
    *,
    text: str,
    comment_id: str | None = None,
    video_id: str | None = None,
    source: str = "unknown",
    created_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "event_id": str(uuid4()),
        "comment_id": comment_id or str(uuid4()),
        "video_id": video_id,
        "text": str(text),
        "source": source,
        "created_at": created_at,
        "ingested_at": utc_now_iso(),
    }
    if metadata:
        event["metadata"] = metadata
    validate_raw_event(event)
    return event


def validate_raw_event(event: dict[str, Any]) -> None:
    if not isinstance(event, dict):
        raise ValueError("Event must be a JSON object")

    missing = [field for field in RAW_REQUIRED_FIELDS if field not in event]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    if not isinstance(event["text"], str) or not event["text"].strip():
        raise ValueError("Field 'text' must be a non-empty string")

    if not str(event["comment_id"]).strip():
        raise ValueError("Field 'comment_id' must not be empty")


def build_classified_event(
    raw_event: dict[str, Any],
    *,
    prediction: dict[str, Any],
    model_version: str,
    latency_ms: float,
) -> dict[str, Any]:
    validate_raw_event(raw_event)
    return {
        **raw_event,
        "prediction": prediction,
        "model_version": model_version,
        "latency_ms": round(float(latency_ms), 3),
        "classified_at": utc_now_iso(),
    }


def build_dlq_event(
    *,
    error: str,
    stage: str,
    original_event: Any = None,
    original_payload: str | None = None,
) -> dict[str, Any]:
    return {
        "event_id": str(uuid4()),
        "stage": stage,
        "error": error,
        "original_event": original_event,
        "original_payload": original_payload,
        "failed_at": utc_now_iso(),
    }
