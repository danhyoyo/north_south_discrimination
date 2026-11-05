import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virdc_stream.preprocessing import normalize_text


class PreprocessingTests(unittest.TestCase):
    def test_lowercase_url_and_spacing(self):
        self.assertEqual(
            normalize_text("  Xin CHÀO!!! https://example.com  "),
            "xin chào",
        )

    def test_keep_vietnamese_and_underscore(self):
        self.assertEqual(normalize_text("người_miền Nam"), "người_miền nam")

    def test_remove_mention_keep_hashtag_text(self):
        self.assertEqual(normalize_text("@abc #ViệtNam"), "việtnam")

    def test_html_entity_and_zero_width(self):
        self.assertEqual(normalize_text("A&amp;B\u200b C"), "a b c")

    def test_reduce_excessive_repeated_letters(self):
        self.assertEqual(normalize_text("đẹpppp quáaaaa"), "đẹpp quáaa")


if __name__ == "__main__":
    unittest.main()
