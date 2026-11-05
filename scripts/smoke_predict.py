from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virdc_stream.config import settings  # noqa: E402
from virdc_stream.model_service import ModelService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one local PhoBERT prediction")
    parser.add_argument("--text", required=True)
    args = parser.parse_args()

    service = ModelService(settings.model_path)
    result = service.predict(args.text)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
