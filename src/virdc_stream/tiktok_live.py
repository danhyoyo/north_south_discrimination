"""Helpers shared by the TikTok collector and its tests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup


DEFAULT_VIDEO_URL = "https://www.tiktok.com/@gronrav/video/7509503512934370568"


def video_id_from_url(url: str) -> str:
    parts = urlparse(url)
    if parts.hostname not in {"www.tiktok.com", "tiktok.com"}:
        raise ValueError("Expected a tiktok.com video URL")
    segments = [part for part in parts.path.split("/") if part]
    if len(segments) < 3 or segments[-2] != "video" or not segments[-1].isdigit():
        raise ValueError("Expected a TikTok URL ending in /video/<numeric-id>")
    return segments[-1]


def extract_comments(html: str, video_id: str) -> list[dict[str, str]]:
    """Read currently rendered top-level comments from TikTok's comment panel.

    This is a browser DOM snapshot, not a complete TikTok comment export.
    """
    soup = BeautifulSoup(html, "html.parser")
    comments = []
    for text_node in soup.select('[data-e2e="comment-level-1"]'):
        text = text_node.get_text(" ", strip=True)
        if not text:
            continue
        wrapper = text_node.find_parent(
            "div", class_=lambda value: bool(value and "DivCommentObjectWrapper" in value)
        )
        if wrapper is None:
            continue
        username_node = wrapper.select_one('[data-e2e="comment-username-1"]')
        profile = (username_node.select_one("a") or username_node.find_parent("a")) if username_node else None
        username = profile.get_text(" ", strip=True) if profile else (
            username_node.get_text(" ", strip=True) if username_node else ""
        )
        profile_href = profile.get("href", "") if profile else ""
        identity = f"{video_id}\0{profile_href}\0{text}"
        comment_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        comments.append({"comment_id": comment_id, "text": text,
                         "username": username, "profile_url": profile_href})
    return comments


def atomic_write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
