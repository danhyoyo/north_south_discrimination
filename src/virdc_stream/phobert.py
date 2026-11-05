from __future__ import annotations

from underthesea import word_tokenize

LABELS = ("khác", "ủng hộ", "phân biệt")


def segment_text(normalized_text: str) -> str:
    """Use identical word segmentation for training and inference."""
    return word_tokenize(normalized_text, format="text")
