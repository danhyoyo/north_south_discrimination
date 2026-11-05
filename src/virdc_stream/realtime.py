from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Any

from .database import connect_database, save_classified_event
from .event_schema import build_classified_event, utc_now_iso, validate_raw_event
from .model_service import ModelService


class SQLiteClassifierWorker:
    """Run PhoBERT in one background thread and persist results to SQLite."""

    def __init__(
        self,
        *,
        model_path: str | Path,
        database_path: str | Path,
        queue_size: int = 1000,
    ) -> None:
        self.model = ModelService(model_path)
        self.database_path = Path(database_path)
        self.queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=queue_size)
        self._thread = threading.Thread(target=self._run, name="phobert-sqlite", daemon=True)
        self._lock = threading.Lock()
        self._started = False
        self._stats: dict[str, Any] = {
            "queued": 0,
            "classified": 0,
            "failed": 0,
            "dropped": 0,
            "last_classified_at": None,
            "last_error": None,
        }

    @property
    def model_version(self) -> str:
        return self.model.model_version

    def start(self) -> None:
        if not self._started:
            self._thread.start()
            self._started = True

    def submit(self, event: dict[str, Any]) -> bool:
        validate_raw_event(event)
        if not self._started:
            raise RuntimeError("Classifier worker has not been started")
        try:
            self.queue.put_nowait(event)
        except queue.Full:
            with self._lock:
                self._stats["dropped"] += 1
                self._stats["last_error"] = "Classifier queue is full"
            return False
        with self._lock:
            self._stats["queued"] += 1
        return True

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {**self._stats, "pending": self.queue.qsize()}

    def close(self, *, wait: bool = True) -> None:
        if not self._started:
            return
        if wait:
            self.queue.join()
        self.queue.put(None)
        self._thread.join(timeout=30)
        self._started = False

    def _run(self) -> None:
        connection = connect_database(self.database_path)
        try:
            while True:
                event = self.queue.get()
                try:
                    if event is None:
                        return
                    started = time.perf_counter()
                    prediction = self.model.predict(event["text"])
                    classified = build_classified_event(
                        event,
                        prediction=prediction,
                        model_version=self.model.model_version,
                        latency_ms=(time.perf_counter() - started) * 1000,
                    )
                    save_classified_event(connection, classified)
                    with self._lock:
                        self._stats["classified"] += 1
                        self._stats["last_classified_at"] = utc_now_iso()
                        self._stats["last_error"] = None
                except Exception as exc:
                    with self._lock:
                        self._stats["failed"] += 1
                        self._stats["last_error"] = f"{type(exc).__name__}: {exc}"
                finally:
                    self.queue.task_done()
        finally:
            connection.close()
