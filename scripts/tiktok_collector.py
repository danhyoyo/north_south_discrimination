from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virdc_stream.config import settings  # noqa: E402
from virdc_stream.event_schema import build_raw_event, utc_now_iso  # noqa: E402
from virdc_stream.realtime import SQLiteClassifierWorker  # noqa: E402
from virdc_stream.tiktok_live import (  # noqa: E402
    DEFAULT_VIDEO_URL, atomic_write_json, extract_comments, video_id_from_url,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Poll TikTok comments, classify them and save to SQLite")
    parser.add_argument("--video-url", default=DEFAULT_VIDEO_URL)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--headless", action="store_true", help="Run Chrome without a visible window")
    parser.add_argument(
        "--profile-dir", default="chrome_profile",
        help="Profile directory under data/state (a run-specific fallback is used if it is locked)",
    )
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    video_id = video_id_from_url(args.video_url)
    state_dir = ROOT / "data" / "state"
    seen_path = state_dir / f"tiktok_seen_{video_id}.json"
    status_path = state_dir / f"tiktok_status_{video_id}.json"
    try:
        seen = set(json.loads(seen_path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        seen = set()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        sys.path.insert(0, str(ROOT / "vendor" / "playwright"))
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise SystemExit("Playwright chưa cài. Chạy: python -m pip install -r requirements-live.txt") from exc

    worker = SQLiteClassifierWorker(
        model_path=settings.model_path,
        database_path=settings.database_path,
        queue_size=settings.classifier_queue_size,
    )
    worker.start()
    print(f"Watching {args.video_url} every {args.interval:g}s")
    with sync_playwright() as playwright:
        profile_path = state_dir / args.profile_dir
        launch_options = {
            "channel": "chrome",
            "headless": args.headless,
            "viewport": {"width": 1300, "height": 900},
        }
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_path), **launch_options
            )
        except Exception as first_error:
            # Chrome refuses a second process using the same profile. Keep the
            # collector usable while another Chrome window is open by isolating
            # this run; the user can close Chrome and rerun to reuse the login.
            fallback_path = state_dir / f"chrome_profile_run_{os.getpid()}"
            print(
                f"Chrome profile is locked ({profile_path}). "
                f"Using {fallback_path} for this run; close Chrome and rerun "
                "to reuse the saved profile.",
                file=sys.stderr,
            )
            try:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(fallback_path), **launch_options
                )
            except Exception:
                raise first_error
        page = context.pages[0] if context.pages else context.new_page()
        try:
            while True:
                started = time.monotonic()
                status = {"video_id": video_id, "video_url": args.video_url,
                          "checked_at": utc_now_iso(), "interval_seconds": args.interval,
                          "new_comments": 0, "visible_comments": 0, "state": "checking"}
                try:
                    challenge = "Drag the slider to fit the puzzle"
                    # Keep the current page open so a person can complete TikTok's verification.
                    if video_id not in page.url or challenge not in page.locator("body").inner_text():
                        page.goto(args.video_url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(1200)
                    if video_id not in page.url:
                        raise RuntimeError(f"Browser redirected to {page.url}; check login or access")
                    if challenge in page.locator("body").inner_text():
                        status["state"] = "verification_required"
                        status["error"] = "TikTok yêu cầu xác minh thanh trượt trong cửa sổ Chrome."
                    else:
                        # TikTok may hide comments until the target video's comment button is opened.
                        button = page.get_by_role("button", name="Read or add comments").first
                        if button.count() and button.is_visible():
                            try:
                                button.click(timeout=3000)
                            except Exception:
                                # A departing guide/backdrop can cover the button.
                                page.keyboard.press("Escape")
                                button.evaluate("element => element.click()")
                            page.wait_for_timeout(900)
                        if challenge in page.locator("body").inner_text():
                            status["state"] = "verification_required"
                            status["error"] = "TikTok yêu cầu xác minh thanh trượt trong cửa sổ Chrome."
                        else:
                            comments = extract_comments(page.content(), video_id)
                            status["visible_comments"] = len(comments)
                            for comment in comments:
                                if comment["comment_id"] in seen:
                                    continue
                                event = build_raw_event(
                                    text=comment["text"], comment_id=comment["comment_id"],
                                    video_id=video_id, source="tiktok-browser",
                                    metadata={"username": comment["username"],
                                              "profile_url": comment["profile_url"],
                                              "video_url": args.video_url},
                                )
                                if not worker.submit(event):
                                    raise RuntimeError("Hàng đợi phân loại đã đầy")
                                seen.add(comment["comment_id"])
                                atomic_write_json(seen_path, sorted(seen))
                                status["new_comments"] += 1
                                print("Queued: " + json.dumps(
                                    {"username": comment["username"], "text": comment["text"][:80]},
                                    ensure_ascii=True,
                                ))
                            status["state"] = "running"
                            status.update(worker.stats())
                except Exception as exc:
                    status["state"] = "error"
                    status["error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
                    print(status["error"], file=sys.stderr)
                atomic_write_json(status_path, status)
                time.sleep(max(0, args.interval - (time.monotonic() - started)))
        except KeyboardInterrupt:
            print("Stopping collector...")
        finally:
            context.close()
            worker.close(wait=True)


if __name__ == "__main__":
    main()
