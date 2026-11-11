from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virdc_stream.data_prep import prepare_all_sources, prepare_split, remove_cross_split_leakage  # noqa: E402
from virdc_stream.data_prep import ALLOWED_LABELS  # noqa: E402
from virdc_stream.preprocessing import PREPROCESSING_VERSION  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean ViRDC train/val/test before model training"
    )
    parser.add_argument("--source-dir", default="data/source")
    parser.add_argument("--output-dir", default="data/processed")
    parser.add_argument("--report", default="artifacts/data_report.json")
    parser.add_argument(
        "--protocol", choices=("upstream", "leakage-safe", "all-sources"), default="upstream",
        help="upstream: published TikTok splits; leakage-safe: clean TikTok splits; all-sources: grouped split of aggregate data",
    )
    parser.add_argument(
        "--keep-cross-split-duplicates",
        action="store_true",
        help="Không loại sentence trùng giữa train/val/test. Không khuyến nghị khi benchmark.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)
    report_path = Path(args.report)

    splits = {}
    split_reports = {}

    if args.protocol == "all-sources":
        input_path = source_dir / "alldata.csv"
        if not input_path.exists():
            raise SystemExit(f"Missing {input_path}. Run python scripts/download_dataset.py --include-all-sources")
        splits, report = prepare_all_sources(input_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, frame in splits.items():
            frame[["sentence", "label"]].to_csv(output_dir / f"{name}.csv", index=False)
            print(f"{name:>5}: {len(frame):,} rows -> {output_dir / f'{name}.csv'}")
            print("       labels:", json.dumps(frame["label"].value_counts().to_dict()))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Data report -> {report_path}")
        return

    if args.protocol == "upstream":
        for split_name in ("train", "val", "test"):
            input_path = source_dir / f"{split_name}.csv"
            if not input_path.exists():
                raise SystemExit(f"Missing {input_path}. Run scripts/download_dataset.py first.")
            frame = pd.read_csv(input_path)
            if not {"sentence", "label"}.issubset(frame.columns):
                raise ValueError(f"{input_path}: expected sentence and label columns")
            if not frame["label"].dropna().isin(ALLOWED_LABELS).all():
                raise ValueError(f"{input_path}: unexpected label in published split")
            splits[split_name] = frame[["sentence", "label"]].dropna().copy()
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, frame in splits.items():
            frame.to_csv(output_dir / f"{name}.csv", index=False)
            print(f"{name:>5}: {len(frame):,} published rows -> {output_dir / f'{name}.csv'}")
            print("       labels:", json.dumps(frame["label"].value_counts().to_dict()))
        overlap = {
            f"{a}_{b}_unique_text_overlap": len(set(splits[a]["sentence"]) & set(splits[b]["sentence"]))
            for a, b in (("train", "val"), ("train", "test"), ("val", "test"))
        }
        report = {
            "protocol": "upstream-published-tiktok-splits",
            "note": "Published CSV text is already preprocessed and word segmented. Only null rows are removed; duplicates and split assignment are preserved. The upstream repository does not publish training/split generation code.",
            "source_dir": str(source_dir),
            "output_dir": str(output_dir),
            "rows": {name: len(frame) for name, frame in splits.items()},
            "split_percentages": {
                name: round(100 * len(frame) / sum(len(item) for item in splits.values()), 2)
                for name, frame in splits.items()
            },
            "labels": {name: frame["label"].value_counts().to_dict() for name, frame in splits.items()},
            "unique_texts": {name: int(frame["sentence"].nunique()) for name, frame in splits.items()},
            "overlap": overlap,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Data report -> {report_path}")
        return

    for split_name in ("train", "val", "test"):
        input_path = source_dir / f"{split_name}.csv"
        if not input_path.exists():
            raise SystemExit(
                f"Missing {input_path}. Run scripts/download_dataset.py first."
            )

        frame, report = prepare_split(input_path)
        splits[split_name] = frame
        split_reports[split_name] = report

    leakage_report = {
        "validation_rows_removed_due_to_train_overlap": 0,
        "test_rows_removed_due_to_train_or_validation_overlap": 0,
    }

    if not args.keep_cross_split_duplicates:
        train, val, test, leakage_report = remove_cross_split_leakage(
            splits["train"], splits["val"], splits["test"]
        )
        splits = {"train": train, "val": val, "test": test}

    output_dir.mkdir(parents=True, exist_ok=True)
    for split_name, frame in splits.items():
        output_path = output_dir / f"{split_name}.csv"
        frame.to_csv(output_path, index=False)
        print(f"{split_name:>5}: {len(frame):,} rows -> {output_path}")
        print("       labels:", json.dumps(frame["label"].value_counts().to_dict()))

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    final_report = {
        "protocol": "leakage-safe",
        "generated_at": generated_at,
        "preprocessing_version": PREPROCESSING_VERSION,
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "cross_split_deduplication_enabled": not args.keep_cross_split_duplicates,
        "splits_before_cross_split_cleanup": split_reports,
        "cross_split_leakage": leakage_report,
        "final_rows": {name: int(len(frame)) for name, frame in splits.items()},
        "final_label_distribution": {
            name: {
                str(k): int(v)
                for k, v in frame["label"].value_counts().to_dict().items()
            }
            for name, frame in splits.items()
        },
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(final_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nData report -> {report_path}")
    print("Data preparation complete. You can now run scripts/train_model.py.")


if __name__ == "__main__":
    main()
