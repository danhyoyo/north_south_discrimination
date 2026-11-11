"""Prepare the three-class old-plus-new dataset used by the realtime web app."""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.model_selection import train_test_split

from .phobert import LABELS
from .preprocessing import PREPROCESSING_VERSION, normalize_text


_NEW_LABELS = {"NON_HATE", "HOSTILE", "PREJUDICIAL"}
_POSITIVE_NEW_LABELS = {"HOSTILE", "PREJUDICIAL"}


def normalize_key(text: object) -> str:
    if pd.isna(text):
        return ""
    return normalize_text(str(text))


def map_old_label(label: object) -> str:
    value = "" if pd.isna(label) else str(label).strip().casefold()
    if value not in LABELS:
        raise ValueError(f"Unknown old label: {label!r}")
    return value


def map_new_labels(north_hate: object, south_hate: object) -> str:
    values = {
        "" if pd.isna(north_hate) else str(north_hate).strip().upper(),
        "" if pd.isna(south_hate) else str(south_hate).strip().upper(),
    }
    unknown = values - _NEW_LABELS
    if unknown:
        raise ValueError(f"Unknown new label(s): {sorted(unknown)}")
    return "phân biệt" if values & _POSITIVE_NEW_LABELS else "khác"


def accentless_sentence(text: str) -> str:
    """Return the notebook's accentless training variant for one sentence."""
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return normalize_text(without_marks.replace("đ", "d").replace("Đ", "D"))


def augment_train_with_accentless_variants(
    splits: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    """Keep originals and add unique, label-consistent accentless rows to train."""
    original_train = splits["train"].copy()
    held_out_sentences = {
        accentless_sentence(text)
        for name in ("val", "test")
        for text in splits[name]["sentence"]
    }
    variants = original_train.assign(
        sentence=original_train["sentence"].map(accentless_sentence)
    )
    label_counts = variants.groupby("sentence")["label"].transform("nunique")
    variants = variants.loc[
        variants["sentence"].ne("")
        & ~variants["sentence"].isin(original_train["sentence"])
        & ~variants["sentence"].isin(held_out_sentences)
        & label_counts.eq(1)
    ].drop_duplicates(subset="sentence")

    augmented = {name: frame.copy() for name, frame in splits.items()}
    augmented["train"] = pd.concat([original_train, variants], ignore_index=True)
    return augmented, {"original_rows": len(original_train), "added_rows": len(variants)}


def _read_csv(path: Path, required: set[str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    return frame


def prepare_merged_three_class(
    old_dir: Path, new_dir: Path, *, seed: int = 42
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Fully deduplicate old data, resplit it, then append clean new rows to train."""
    old_dir = Path(old_dir)
    new_dir = Path(new_dir)
    old_parts: dict[str, pd.DataFrame] = {}
    for split in ("train", "val", "test"):
        path = old_dir / f"{split}.csv"
        frame = _read_csv(path, {"sentence", "label"})
        if frame[["sentence", "label"]].isna().any().any():
            raise ValueError(f"{path}: null sentence or label")
        mapped = frame[["sentence", "label"]].copy()
        mapped["sentence"] = mapped["sentence"].map(normalize_key)
        if mapped["sentence"].eq("").any():
            raise ValueError(f"{path}: blank sentence after preprocessing")
        mapped["label"] = mapped["label"].map(map_old_label)
        old_parts[split] = mapped.reset_index(drop=True)

    original_old_sets = {
        name: set(frame["sentence"])
        for name, frame in old_parts.items()
    }
    original_old_overlap = {
        f"{left}_{right}": int(len(original_old_sets[left] & original_old_sets[right]))
        for left, right in (("train", "val"), ("train", "test"), ("val", "test"))
    }
    old_all = pd.concat(old_parts.values(), ignore_index=True)
    old_grouped_labels = old_all.groupby("sentence")["label"].nunique()
    old_conflicting_keys = set(old_grouped_labels[old_grouped_labels.gt(1)].index)
    old_conflicting_mask = old_all["sentence"].isin(old_conflicting_keys)
    old_nonconflicting = old_all.loc[~old_conflicting_mask].copy()
    old_unique = old_nonconflicting.drop_duplicates(subset=["sentence"], keep="first")
    old_train_val, old_test = train_test_split(
        old_unique,
        test_size=0.15,
        stratify=old_unique["label"],
        random_state=seed,
    )
    old_train, old_val = train_test_split(
        old_train_val,
        test_size=0.15 / 0.85,
        stratify=old_train_val["label"],
        random_state=seed,
    )

    new_parts = []
    new_source_rows_by_split: dict[str, int] = {}
    for split in ("train", "val", "test"):
        path = new_dir / f"{split}.csv"
        frame = _read_csv(path, {"comment", "north_hate", "south_hate"})
        if frame[["comment", "north_hate", "south_hate"]].isna().any().any():
            raise ValueError(f"{path}: null required value")
        part = frame[["comment", "north_hate", "south_hate"]].copy()
        part["_key"] = part["comment"].map(normalize_key)
        if part["_key"].eq("").any():
            raise ValueError(f"{path}: blank comment after preprocessing")
        part["_label"] = [
            map_new_labels(north, south)
            for north, south in zip(part["north_hate"], part["south_hate"], strict=True)
        ]
        new_source_rows_by_split[split] = int(len(part))
        new_parts.append(part)

    new_all = pd.concat(new_parts, ignore_index=True)
    grouped_labels = new_all.groupby("_key")["_label"].nunique()
    conflicting_keys = set(grouped_labels[grouped_labels.gt(1)].index)
    conflicting_mask = new_all["_key"].isin(conflicting_keys)
    nonconflicting = new_all.loc[~conflicting_mask].copy()
    new_unique = nonconflicting.drop_duplicates(subset=["_key"], keep="first").copy()

    all_old_keys = set(old_all["sentence"])
    overlap_mask = new_unique["_key"].isin(all_old_keys)
    retained = new_unique.loc[~overlap_mask]
    new_rows = pd.DataFrame(
        {"sentence": retained["_key"], "label": retained["_label"]}
    ).reset_index(drop=True)

    splits = {
        "train": pd.concat([old_train, new_rows], ignore_index=True),
        "val": old_val.reset_index(drop=True),
        "test": old_test.reset_index(drop=True),
    }
    final_sets = {name: set(frame["sentence"]) for name, frame in splits.items()}
    final_overlap = {
        f"{left}_{right}": int(len(final_sets[left] & final_sets[right]))
        for left, right in (("train", "val"), ("train", "test"), ("val", "test"))
    }
    report: dict[str, Any] = {
        "protocol": "three-class-fully-deduplicated-old-resplit-new-in-train",
        "preprocessing_version": PREPROCESSING_VERSION,
        "labels": list(LABELS),
        "seed": seed,
        "old_split_strategy": "stratified 70/15/15 after full normalized-text deduplication",
        "new_non_hate_mapping": "khác",
        "old_source_rows_by_split": {
            name: int(len(frame)) for name, frame in old_parts.items()
        },
        "old_source_rows": int(len(old_all)),
        "old_original_cross_split_unique_text_overlap": original_old_overlap,
        "old_conflicting_text_groups_removed": int(len(old_conflicting_keys)),
        "old_conflicting_rows_removed": int(old_conflicting_mask.sum()),
        "old_duplicate_rows_removed": int(len(old_nonconflicting) - len(old_unique)),
        "old_unique_nonconflicting_rows": int(len(old_unique)),
        "new_source_rows_by_split": new_source_rows_by_split,
        "new_source_rows": int(len(new_all)),
        "new_duplicate_rows_removed": int(len(nonconflicting) - len(new_unique)),
        "new_conflicting_duplicate_text_groups": int(len(conflicting_keys)),
        "new_conflicting_duplicate_rows_removed": int(conflicting_mask.sum()),
        "new_rows_removed_for_old_overlap": int(overlap_mask.sum()),
        "new_rows_retained": int(len(new_rows)),
        "final_rows": {name: int(len(frame)) for name, frame in splits.items()},
        "final_cross_split_unique_text_overlap": final_overlap,
        "final_label_distribution": {
            name: {
                str(label): int(count)
                for label, count in frame["label"].value_counts().items()
            }
            for name, frame in splits.items()
        },
    }
    return splits, report
