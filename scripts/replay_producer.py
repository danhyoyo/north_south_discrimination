from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virdc_stream.config import settings  # noqa: E402
from virdc_stream.event_schema import build_raw_event  # noqa: E402
from virdc_stream.realtime import SQLiteClassifierWorker  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify dataset rows into SQLite")
    parser.add_argument("--file", default="data/processed/test.csv")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between comments")
    parser.add_argument("--limit", type=int, default=0, help="0 means all rows")
    return parser.parse_args()


def choose_text(row: pd.Series) -> str:
    for column in ("original_sentence", "sentence", "text", "processed_text"):
        if column in row and pd.notna(row[column]):
            return str(row[column])
    raise ValueError("Could not find sentence/text/processed_text column")


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.file)
    if args.limit > 0:
        df = df.head(args.limit)

    worker = SQLiteClassifierWorker(
        model_path=settings.model_path,
        database_path=settings.database_path,
        queue_size=settings.classifier_queue_size,
    )
    worker.start()
    total = len(df)

    for position, (index, row) in enumerate(df.iterrows(), start=1):
        text = choose_text(row)
        metadata = {}
        if "label" in df.columns and pd.notna(row.get("label")):
            metadata["ground_truth"] = str(row["label"])

        event = build_raw_event(
            text=text,
            comment_id=f"replay-{index}",
            video_id="dataset-demo",
            source="dataset-replay",
            metadata=metadata or None,
        )
        while not worker.submit(event):
            time.sleep(0.1)
        print(f"[{position}/{total}] queued -> {text[:90]}")
        if args.delay > 0:
            time.sleep(args.delay)
    worker.close(wait=True)
    stats = worker.stats()
    print(f"Saved {stats['classified']} predictions to {settings.database_path}")


if __name__ == "__main__":
    main()
