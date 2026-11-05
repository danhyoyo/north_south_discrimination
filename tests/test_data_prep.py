import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virdc_stream.data_prep import prepare_all_sources, prepare_split, remove_cross_split_leakage


class DataPrepTests(unittest.TestCase):
    def test_prepare_split_removes_duplicate_and_conflict(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "train.csv"
            pd.DataFrame(
                {
                    "sentence": [
                        "Xin CHÀO!!!",
                        "xin chào",
                        "câu xung đột",
                        "CÂU XUNG ĐỘT",
                        None,
                    ],
                    "label": [
                        "khác",
                        "khác",
                        "khác",
                        "phân biệt",
                        "khác",
                    ],
                }
            ).to_csv(path, index=False)

            frame, report = prepare_split(path)

            self.assertEqual(len(frame), 1)
            self.assertEqual(frame.iloc[0]["sentence"], "xin chào")
            self.assertEqual(report["removed"]["duplicate_rows"], 1)
            self.assertEqual(report["removed"]["conflicting_label_rows"], 2)
            self.assertEqual(report["removed"]["null_text_or_label"], 1)

    def test_cross_split_leakage(self):
        train = pd.DataFrame({"sentence": ["a"], "label": ["khác"]})
        val = pd.DataFrame({"sentence": ["a", "b"], "label": ["khác", "khác"]})
        test = pd.DataFrame({"sentence": ["a", "b", "c"], "label": ["khác"] * 3})

        _, val_clean, test_clean, report = remove_cross_split_leakage(train, val, test)

        self.assertEqual(val_clean["sentence"].tolist(), ["b"])
        self.assertEqual(test_clean["sentence"].tolist(), ["c"])
        self.assertEqual(report["validation_rows_removed_due_to_train_overlap"], 1)
        self.assertEqual(
            report["test_rows_removed_due_to_train_or_validation_overlap"], 2
        )

    def test_all_sources_split_keeps_text_groups_separate(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "alldata.csv"
            rows = [
                (f"câu {label} {number}", float(label))
                for label in (0, 1, 2)
                for number in range(30)
            ]
            rows += [("câu 2 0", 2.0), ("xung đột", 0.0), ("xung đột", 1.0)]
            pd.DataFrame(rows, columns=["processed_comment", "label"]).to_csv(path, index=False)
            splits, report = prepare_all_sources(path)

            self.assertEqual(report["excluded_conflicting_label_rows"], 2)
            self.assertEqual(len(set(splits["train"].sentence) & set(splits["val"].sentence)), 0)
            self.assertEqual(len(set(splits["train"].sentence) & set(splits["test"].sentence)), 0)
            self.assertEqual(len(set(splits["val"].sentence) & set(splits["test"].sentence)), 0)
            self.assertEqual(len(set(splits["train"].label.value_counts())), 1)


if __name__ == "__main__":
    unittest.main()
