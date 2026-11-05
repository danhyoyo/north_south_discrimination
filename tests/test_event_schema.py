import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virdc_stream.event_schema import build_classified_event, build_raw_event, validate_raw_event


class EventSchemaTests(unittest.TestCase):
    def test_build_raw_event(self):
        event = build_raw_event(text="hello", source="test")
        validate_raw_event(event)
        self.assertEqual(event["text"], "hello")
        self.assertEqual(event["source"], "test")

    def test_empty_text_rejected(self):
        with self.assertRaises(ValueError):
            build_raw_event(text="   ", source="test")

    def test_classified_event(self):
        raw = build_raw_event(text="hello", source="test")
        output = build_classified_event(
            raw,
            prediction={"label": "khác", "score": 0.9, "is_discrimination": False},
            model_version="test-v1",
            latency_ms=1.23456,
        )
        self.assertEqual(output["model_version"], "test-v1")
        self.assertEqual(output["prediction"]["label"], "khác")


if __name__ == "__main__":
    unittest.main()
