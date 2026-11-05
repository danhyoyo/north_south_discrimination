from __future__ import annotations

import html
import re
import unicodedata


URL_RE = re.compile(r"https?://\S+|www\.\S+", flags=re.IGNORECASE)
MENTION_RE = re.compile(r"(?<!\w)@[\w.]+", flags=re.UNICODE)
WHITESPACE_RE = re.compile(r"\s+")
NON_WORD_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
# Chỉ rút gọn khi một chữ cái lặp >= 3 lần: "đẹpppp" -> "đẹpp".
# Giữ 2 ký tự để không làm mất hoàn toàn tín hiệu nhấn mạnh trên mạng xã hội.
REPEATED_LETTER_RE = re.compile(r"([^\W\d_])\1{2,}", flags=re.UNICODE | re.IGNORECASE)

PREPROCESSING_VERSION = "social-clean-v2"


def normalize_text(text: str) -> str:
    """Chuẩn hoá nhẹ, dùng CHUNG cho data preparation, training và realtime inference.

    Chuẩn hoá đầu vào chung cho chuẩn bị dữ liệu, PhoBERT và realtime inference:
    - giảm nhiễu kỹ thuật (URL, mention, zero-width, HTML entity, whitespace);
    - giữ chữ tiếng Việt, chữ số và dấu gạch dưới của word segmentation;
    - không remove stopword/không ép word segmentation để serving đơn giản;
    - giảm kéo dài ký tự quá mức nhưng vẫn giữ 2 ký tự để biểu diễn nhấn mạnh.
    """
    if text is None:
        return ""

    value = html.unescape(str(text))
    value = unicodedata.normalize("NFC", value)
    value = ZERO_WIDTH_RE.sub("", value)
    value = value.lower().strip()

    value = URL_RE.sub(" ", value)
    value = MENTION_RE.sub(" ", value)

    # Giữ nội dung hashtag, chỉ bỏ dấu '#': "#ViệtNam" -> "việtnam".
    value = value.replace("#", " ")

    # Dataset có các token dạng "đồng_bào"; \w giữ underscore nên không phá tín hiệu này.
    value = NON_WORD_RE.sub(" ", value)
    value = REPEATED_LETTER_RE.sub(lambda m: m.group(1) * 2, value)
    value = WHITESPACE_RE.sub(" ", value).strip()
    return value


def text_features(text: str) -> dict[str, int]:
    """Một vài feature thống kê để audit dataset; không đưa trực tiếp vào model."""
    normalized = normalize_text(text)
    return {
        "char_length": len(normalized),
        "word_count": len(normalized.split()) if normalized else 0,
    }
