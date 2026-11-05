from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.live_dashboard import read_history
from virdc_stream.database import connect_database, save_classified_event
from virdc_stream.event_schema import build_classified_event, build_raw_event
from virdc_stream.live_schema import live_stream_id, parse_live_url
from virdc_stream.tiktok_live import extract_comments, video_id_from_url


def test_extract_comments_and_dedupe_identity():
    html = """<div class='DivCommentObjectWrapper'>
      <a href='/@alice'><span data-e2e='comment-username-1'>Alice</span></a>
      <span data-e2e='comment-level-1'>Xin chào miền Bắc</span>
      <span data-e2e='comment-level-2'>Reply excluded</span>
    </div>"""
    comments = extract_comments(html, "7509503512934370568")
    assert len(comments) == 1
    assert comments[0]["text"] == "Xin chào miền Bắc"
    assert comments[0]["username"] == "Alice"
    assert comments == extract_comments(html, "7509503512934370568")
    assert comments[0]["comment_id"] != extract_comments(html, "999")[0]["comment_id"]


def test_extract_tiktok_author_wrapper():
    html = """<div class='css-abc--DivCommentObjectWrapper xyz'>
      <div data-e2e='comment-username-1'><div><a href='/@gronrav'><p>Grön Räv</p></a></div><p>· Creator</p></div>
      <span data-e2e='comment-level-1'>ủa dc k ta</span>
    </div>"""
    item = extract_comments(html, "7509503512934370568")[0]
    assert item["username"] == "Grön Räv"
    assert item["profile_url"] == "/@gronrav"


def test_video_url_validation():
    assert video_id_from_url("https://www.tiktok.com/@gronrav/video/7509503512934370568") == "7509503512934370568"
    try:
        video_id_from_url("https://example.com/@gronrav/video/7509503512934370568")
    except ValueError:
        pass
    else:
        raise AssertionError("Unexpected host accepted")


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
