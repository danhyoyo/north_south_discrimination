from __future__ import annotations

LABELS = ("khác", "ủng hộ", "phân biệt")


def segment_text(normalized_text: str) -> str:
    """Use identical word segmentation for training and inference."""
    from underthesea import word_tokenize

    return word_tokenize(normalized_text, format="text")
