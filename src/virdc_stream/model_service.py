from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from .event_schema import UNCLASSIFIED_LABEL
from .phobert import LABELS, segment_text
from .preprocessing import PREPROCESSING_VERSION, normalize_text


class ModelService:
    """Load a fine tuned PhoBERT directory once for realtime inference."""

    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path)
        metadata_path = self.model_path / "metadata.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(f"PhoBERT model not found at {self.model_path}. Run python scripts/train_model.py")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("preprocessing_version") != PREPROCESSING_VERSION:
            raise ValueError("Preprocessing version mismatch; prepare data and retrain the model")
        if metadata.get("segmentation") not in ("underthesea-word_tokenize-text", "published-vncorenlp"):
            raise ValueError("Word segmentation version mismatch; retrain the model")
        if metadata["segmentation"] == "published-vncorenlp":
            warnings.warn(
                "The published CSVs were segmented with VnCoreNLP; live inference uses Underthesea. "
                "For exact preprocessing parity, deploy the original VnCoreNLP pipeline.",
                stacklevel=2,
            )
        if tuple(metadata.get("known_labels", [])) != LABELS:
            raise ValueError("Model label mapping does not match this application")
        self.model_version = metadata["model_version"]
        self.positive_label = metadata["positive_label"]
        self.max_length = int(metadata["max_length"])

        load_path = self.model_path
        if not (load_path / "config.json").is_file():
            # A training-run directory stores the exported metadata at its root
            # and the best Hugging Face model under checkpoints/checkpoint-*/.
            trainer_state_path = self.model_path / "trainer_state.json"
            if not trainer_state_path.is_file():
                raise FileNotFoundError(f"PhoBERT model files not found at {self.model_path}")
            trainer_state = json.loads(trainer_state_path.read_text(encoding="utf-8"))
            best_checkpoint = trainer_state.get("best_model_checkpoint")
            if not best_checkpoint:
                raise FileNotFoundError(f"Best PhoBERT checkpoint not recorded in {trainer_state_path}")
            checkpoint_name = str(best_checkpoint).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
            load_path = self.model_path / "checkpoints" / checkpoint_name
            if not (load_path / "config.json").is_file():
                raise FileNotFoundError(f"Best PhoBERT checkpoint not found at {load_path}")

        self.tokenizer = AutoTokenizer.from_pretrained(load_path, use_fast=False)
        self.model = AutoModelForSequenceClassification.from_pretrained(load_path)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.model.eval()

    def predict(self, text: str) -> dict[str, Any]:
        normalized = normalize_text(text)
        if not normalized:
            return {
                "label": UNCLASSIFIED_LABEL,
                "score": None,
                "is_discrimination": False,
                "probabilities": {},
                "normalized_text": normalized,
            }
        encoded = self.tokenizer(segment_text(normalized), return_tensors="pt", truncation=True, max_length=self.max_length)
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with torch.inference_mode():
            probabilities_tensor = torch.softmax(self.model(**encoded).logits[0], dim=-1)
        probabilities = {label: round(float(probabilities_tensor[i]), 6) for i, label in enumerate(LABELS)}
        predicted_label = LABELS[int(torch.argmax(probabilities_tensor))]
        return {
            "label": predicted_label,
            "score": probabilities[predicted_label],
            "is_discrimination": predicted_label == self.positive_label,
            "probabilities": probabilities,
            "normalized_text": normalized,
        }
