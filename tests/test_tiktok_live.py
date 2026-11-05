from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.live_dashboard import read_history
from virdc_stream.database import connect_database, save_classified_event
from virdc_stream.event_schema import build_classified_event, build_raw_event
from virdc_stream.live_schema import live_stream_id, parse_live_url
def test_live_url_parsing():
    assert parse_live_url("https://www.tiktok.com/@creator/live") == "creator"
    assert parse_live_url("@creator") == "creator"
    assert live_stream_id("Creator") == "live:creator"
    try:
        parse_live_url("https://www.tiktok.com/@creator/video/123")
    except ValueError:
        pass
    else:
        raise AssertionError("Video URL accepted as LIVE URL")


def test_history_only_target_live_and_latest_duplicate():
    path = ROOT / "data" / "results" / "test_history.db"
    sidecars = [path, Path(str(path) + "-wal"), Path(str(path) + "-shm")]
    for item in sidecars:
        item.unlink(missing_ok=True)
    try:
        raw = build_raw_event(
            text="bình luận thử",
            comment_id="one",
            video_id="live:target",
            source="tiktok-live",
            metadata={"username": "alice"},
        )
        first = build_classified_event(
            raw,
            prediction={"label": "khác", "score": 0.8, "is_discrimination": False},
            model_version="test",
            latency_ms=10,
        )
        second = build_classified_event(
            raw,
            prediction={"label": "phân biệt", "score": 0.9, "is_discrimination": True},
            model_version="test",
            latency_ms=12,
        )
        connection = connect_database(path)
        try:
            save_classified_event(connection, first)
            save_classified_event(connection, second)
        finally:
            connection.close()
        items, total = read_history(path, "live:target")
        assert total == 1
        assert items[0]["comment_id"] == "one"
        assert items[0]["prediction"]["label"] == "phân biệt"
    finally:
        for item in sidecars:
            item.unlink(missing_ok=True)
