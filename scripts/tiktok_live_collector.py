from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virdc_stream.config import settings  # noqa: E402
from virdc_stream.database import save_live_event  # noqa: E402
from virdc_stream.event_schema import build_raw_event, utc_now_iso  # noqa: E402
from virdc_stream.live_schema import live_stream_id, parse_live_url  # noqa: E402
from virdc_stream.realtime import SQLiteClassifierWorker  # noqa: E402
from virdc_stream.tiktok_live import atomic_write_json  # noqa: E402


def _value(obj, name: str, default=None):
    return getattr(obj, name, default) if obj is not None else default


def main() -> None:
    parser = argparse.ArgumentParser(description="Read TikTok LIVE comments and gifts in realtime")
    parser.add_argument(
        "--live-url", default=os.getenv("TIKTOK_LIVE_URL", settings.tiktok_live_url),
        help="TikTok LIVE URL, for example https://www.tiktok.com/@username/live",
    )
    args = parser.parse_args()
    if not args.live_url:
        parser.error("Provide --live-url or set TIKTOK_LIVE_URL")
    unique_id = parse_live_url(args.live_url)
    stream_id = live_stream_id(unique_id)
    status_path = ROOT / "data" / "state" / f"tiktok_live_status_{unique_id.lower()}.json"

    try:
        from TikTokLive import TikTokLiveClient
        from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent, GiftEvent
    except ImportError as exc:
        raise SystemExit("TikTokLive chưa cài. Chạy: python -m pip install -r requirements-live.txt") from exc

    worker = SQLiteClassifierWorker(
        model_path=settings.model_path,
        database_path=settings.database_path,
        queue_size=settings.classifier_queue_size,
    )
    worker.start()
    client = TikTokLiveClient(unique_id=unique_id)
    counters = {"comments_received": 0, "gifts_received": 0}

    def write_status(state: str, **extra) -> None:
        atomic_write_json(status_path, {
            "stream_id": stream_id, "unique_id": unique_id,
            "live_url": args.live_url, "checked_at": utc_now_iso(),
            "state": state, **counters, **worker.stats(), **extra,
        })

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent) -> None:
        write_status("connected", room_id=str(_value(client, "room_id", "")))
        print(f"Connected to @{unique_id} (room: {_value(client, 'room_id', '')})")

    @client.on(CommentEvent)
    async def on_comment(event: CommentEvent) -> None:
        text = str(_value(event, "comment", "")).strip()
        if not text:
            return
        user = _value(event, "user")
        username = str(_value(user, "nickname", "")).strip()
        user_unique_id = str(_value(user, "unique_id", "")).strip()
        comment_id = str(
            _value(event, "comment_id", "")
            or _value(event, "message_id", "")
            or f"{stream_id}:{uuid4()}"
        )
        raw_event = build_raw_event(
            text=text, comment_id=comment_id, video_id=stream_id,
            source="tiktok-live", metadata={
                "username": username, "unique_id": user_unique_id,
                "profile_url": f"https://www.tiktok.com/@{user_unique_id}" if user_unique_id else "",
                "live_url": args.live_url, "collector": "TikTokLive",
            },
        )
        counters["comments_received"] += 1
        if not worker.submit(raw_event):
            write_status("error", error="Hàng đợi phân loại đã đầy")
            return
        write_status("connected", last_comment_at=utc_now_iso())
        print("COMMENT " + json.dumps({
            "username": username or "unknown", "text": text[:100]
        }, ensure_ascii=True))

    @client.on(GiftEvent)
    async def on_gift(event: GiftEvent) -> None:
        user = _value(event, "user")
        gift = _value(event, "gift")
        gift_event = {
            "event_id": str(uuid4()), "event_type": "gift",
            "stream_id": stream_id, "unique_id": unique_id,
            "live_url": args.live_url, "occurred_at": utc_now_iso(),
            "user": {
                "nickname": str(_value(user, "nickname", "")),
                "unique_id": str(_value(user, "unique_id", "")),
            },
            "gift": {
                "name": str(_value(gift, "name", "")),
                "type": _value(gift, "type"),
                "repeat_count": _value(event, "repeat_count", 1),
                "repeat_end": _value(event, "repeat_end", 0),
                "streaking": bool(_value(event, "streaking", False)),
            },
        }
        save_live_event(settings.database_path, gift_event)
        counters["gifts_received"] += 1
        write_status("connected", last_gift_at=utc_now_iso())
        print("GIFT " + json.dumps({
            "unique_id": gift_event["user"]["unique_id"],
            "name": gift_event["gift"]["name"],
            "repeat_count": gift_event["gift"]["repeat_count"],
        }, ensure_ascii=True))

    @client.on(DisconnectEvent)
    async def on_disconnect(event: DisconnectEvent) -> None:
        write_status("disconnected", reason=str(_value(event, "reason", "")))
        print("Disconnected from LIVE")

    write_status("connecting")
    print(f"Connecting to @{unique_id} via TikTok LIVE")
    try:
        client.run(fetch_gift_info=True)
    except KeyboardInterrupt:
        print("Stopping TikTok LIVE collector...")
    except Exception as exc:
        write_status("error", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        worker.close(wait=True)


if __name__ == "__main__":
    main()
