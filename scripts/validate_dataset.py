from __future__ import annotations

from pathlib import Path

import pandas as pd


EXPECTED = {
    "train.csv": {"sentence", "label"},
    "val.csv": {"sentence", "label"},
    "test.csv": {"sentence", "label"},
    "tiktok.csv": {"text", "label", "processed_text"},
}


def main() -> None:
    root = Path("data/source")
    errors: list[str] = []

    for filename, required_columns in EXPECTED.items():
        path = root / filename
        if not path.exists():
            errors.append(f"Missing {path}")
            continue

        df = pd.read_csv(path)
        missing = required_columns - set(df.columns)
        if missing:
            errors.append(f"{filename}: missing columns {sorted(missing)}")
            continue

        print(f"\n{filename}: {len(df):,} rows")
        print(f"columns: {list(df.columns)}")
        if "label" in df.columns:
            print("labels:")
            print(df["label"].value_counts(dropna=False).to_string())

    if errors:
        print("\nValidation failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("\nDataset looks valid.")


if __name__ == "__main__":
    main()
