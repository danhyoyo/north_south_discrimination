from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    model_path: Path = Path(os.getenv("MODEL_PATH", "artifacts/phobert"))
    database_path: Path = Path(os.getenv("DATABASE_PATH", "data/results/analysis.db"))
    classifier_queue_size: int = int(os.getenv("CLASSIFIER_QUEUE_SIZE", "1000"))
    tiktok_live_url: str = os.getenv("TIKTOK_LIVE_URL", "")


settings = Settings()
