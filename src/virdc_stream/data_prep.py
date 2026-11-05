from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.model_selection import train_test_split

from .preprocessing import normalize_text, text_features


ALLOWED_LABELS = ("khác", "ủng hộ", "phân biệt")
NUMERIC_LABELS = {0.0: "khác", 1.0: "phân biệt", 2.0: "ủng hộ"}


def prepare_all_sources(path: Path, *, seed: int = 42) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Split the published, already processed aggregate without cross-split text overlap."""
    raw = pd.read_csv(path)
    if not {"processed_comment", "label"}.issubset(raw.columns):
        raise ValueError(f"{path}: expected processed_comment and label columns")
    work = raw[["processed_comment", "label"]].dropna().copy()
    work["label"] = pd.to_numeric(work["label"], errors="coerce").map(NUMERIC_LABELS)
    work = work.dropna(subset=["label"])
    work["sentence"] = work["processed_comment"].astype(str).str.strip()
    work = work.loc[work["sentence"].ne("")].copy()
    conflicting = work.groupby("sentence")["label"].nunique().gt(1)
    conflict_texts = set(conflicting[conflicting].index)
    conflict_rows = int(work["sentence"].isin(conflict_texts).sum())
    work = work.loc[~work["sentence"].isin(conflict_texts)]
    unique = work[["sentence", "label"]].drop_duplicates(subset=["sentence"]).reset_index(drop=True)
    train_val, test = train_test_split(unique, test_size=0.2, stratify=unique["label"], random_state=seed)
    train, val = train_test_split(train_val, test_size=0.25, stratify=train_val["label"], random_state=seed)
    # Oversample the training split only. Validation and test remain independent.
    target = int(train["label"].value_counts().max())
    train = pd.concat(
        [group.sample(n=target, replace=len(group) < target, random_state=seed)
         for _, group in train.groupby("label", sort=True)],
        ignore_index=True,
    ).sample(frac=1, random_state=seed).reset_index(drop=True)
    splits = {"train": train, "val": val.reset_index(drop=True), "test": test.reset_index(drop=True)}
    report = {
        "protocol": "all-sources-grouped-split",
        "source_file": str(path),
        "source_rows": len(raw),
        "excluded_null_or_unmapped_label_rows": len(raw) - len(work) - conflict_rows,
        "excluded_conflicting_label_rows": conflict_rows,
        "unique_nonconflicting_texts": len(unique),
        "train_balancing": "oversample training only after splitting",
        "rows": {name: len(frame) for name, frame in splits.items()},
        "labels": {name: frame["label"].value_counts().to_dict() for name, frame in splits.items()},
        "unique_texts": {name: int(frame["sentence"].nunique()) for name, frame in splits.items()},
        "cross_split_unique_text_overlap": 0,
    }
    return splits, report


def normalize_label(value: object) -> str:
    return str(value).strip().lower()


def _counter(series: pd.Series) -> dict[str, int]:
    counts = Counter(series.astype(str).tolist())
    return {label: int(counts.get(label, 0)) for label in ALLOWED_LABELS}


def prepare_split(
    path: Path,
    *,
    text_column: str = "sentence",
    label_column: str = "label",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = pd.read_csv(path)
    required = {text_column, label_column}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")

    original_rows = len(df)
    work = df[[text_column, label_column]].copy()
    work.columns = ["original_sentence", "label"]

    null_mask = work["original_sentence"].isna() | work["label"].isna()
    removed_null = int(null_mask.sum())
    work = work.loc[~null_mask].copy()

    work["label"] = work["label"].map(normalize_label)
    invalid_label_mask = ~work["label"].isin(ALLOWED_LABELS)
    invalid_labels = (
        work.loc[invalid_label_mask, "label"].value_counts(dropna=False).to_dict()
    )
    removed_invalid_labels = int(invalid_label_mask.sum())
    work = work.loc[~invalid_label_mask].copy()

    work["sentence"] = work["original_sentence"].map(normalize_text)
    empty_mask = work["sentence"].eq("")
    removed_empty = int(empty_mask.sum())
    work = work.loc[~empty_mask].copy()

    # Nếu cùng một normalized sentence có nhiều nhãn khác nhau, bỏ TOÀN BỘ sentence đó.
    label_cardinality = work.groupby("sentence")["label"].nunique()
    conflicting_sentences = set(label_cardinality[label_cardinality > 1].index)
    conflict_mask = work["sentence"].isin(conflicting_sentences)
    removed_conflicts = int(conflict_mask.sum())
    work = work.loc[~conflict_mask].copy()

    before_dedupe = len(work)
    work = work.drop_duplicates(subset=["sentence", "label"], keep="first").copy()
    removed_duplicates = before_dedupe - len(work)

    features = work["sentence"].map(text_features)
    work["char_length"] = features.map(lambda item: item["char_length"])
    work["word_count"] = features.map(lambda item: item["word_count"])

    # Cột sentence là input canonical mà train_model.py dùng.
    work = work[
        ["sentence", "label", "original_sentence", "char_length", "word_count"]
    ].reset_index(drop=True)

    report = {
        "file": str(path),
        "rows_original": int(original_rows),
        "rows_after_cleaning": int(len(work)),
        "removed": {
            "null_text_or_label": removed_null,
            "invalid_label": removed_invalid_labels,
            "empty_after_normalization": removed_empty,
            "conflicting_label_rows": removed_conflicts,
            "duplicate_rows": int(removed_duplicates),
        },
        "invalid_labels": {str(k): int(v) for k, v in invalid_labels.items()},
        "label_distribution": _counter(work["label"]),
        "text_stats": {
            "char_length_mean": float(work["char_length"].mean()) if len(work) else 0.0,
            "char_length_p95": float(work["char_length"].quantile(0.95)) if len(work) else 0.0,
            "word_count_mean": float(work["word_count"].mean()) if len(work) else 0.0,
            "word_count_p95": float(work["word_count"].quantile(0.95)) if len(work) else 0.0,
        },
    }
    return work, report


def remove_cross_split_leakage(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Train có độ ưu tiên cao nhất; val loại câu đã có trong train;
    test loại câu đã có trong train hoặc val.
    """
    train_texts = set(train["sentence"])

    val_overlap_mask = val["sentence"].isin(train_texts)
    val_removed = int(val_overlap_mask.sum())
    val_clean = val.loc[~val_overlap_mask].copy().reset_index(drop=True)

    protected = train_texts | set(val_clean["sentence"])
    test_overlap_mask = test["sentence"].isin(protected)
    test_removed = int(test_overlap_mask.sum())
    test_clean = test.loc[~test_overlap_mask].copy().reset_index(drop=True)

    return (
        train.reset_index(drop=True),
        val_clean,
        test_clean,
        {
            "validation_rows_removed_due_to_train_overlap": val_removed,
            "test_rows_removed_due_to_train_or_validation_overlap": test_removed,
        },
    )
