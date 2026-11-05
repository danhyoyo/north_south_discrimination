from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from torch.utils.data import Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding, Trainer, TrainingArguments, set_seed

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from virdc_stream.phobert import LABELS, segment_text  # noqa: E402
from virdc_stream.preprocessing import PREPROCESSING_VERSION, normalize_text  # noqa: E402


class TextDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_length, *, already_segmented=False):
        inputs = texts if already_segmented else [segment_text(text) for text in texts]
        self.encodings = tokenizer(inputs, truncation=True, max_length=max_length)
        self.labels = [LABELS.index(label) for label in labels]

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, index):
        return {**{key: value[index] for key, value in self.encodings.items()}, "labels": self.labels[index]}


def read_split(path, *, published_text=False):
    df = pd.read_csv(path)
    missing = {"sentence", "label"} - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    df = df.dropna(subset=["sentence", "label"])
    texts = [str(value).strip() if published_text else normalize_text(value) for value in df["sentence"]]
    labels = df["label"].astype(str).str.strip().tolist()
    invalid = sorted(set(labels) - set(LABELS))
    if invalid:
        raise ValueError(f"{path}: unknown labels {invalid}")
    pairs = [(text, label) for text, label in zip(texts, labels, strict=True) if text]
    if not pairs:
        raise ValueError(f"{path}: no usable rows")
    return [p[0] for p in pairs], [p[1] for p in pairs]


def evaluate(trainer, dataset):
    predicted = np.argmax(trainer.predict(dataset).predictions, axis=-1)
    actual = np.asarray(dataset.labels)
    ids = list(range(len(LABELS)))
    return {
        "rows": len(actual),
        "accuracy": float(accuracy_score(actual, predicted)),
        "macro_f1": float(f1_score(actual, predicted, labels=ids, average="macro", zero_division=0)),
        "labels": list(LABELS),
        "classification_report": classification_report(actual, predicted, labels=ids, target_names=LABELS, output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(actual, predicted, labels=ids).tolist(),
    }


def main():
    parser = argparse.ArgumentParser(description="Fine tune PhoBERT for ViRDC")
    parser.add_argument("--train")
    parser.add_argument("--val")
    parser.add_argument("--test")
    parser.add_argument("--base-model", default="vinai/phobert-base-v2")
    parser.add_argument("--output")
    parser.add_argument("--metrics")
    parser.add_argument("--data-report")
    parser.add_argument("--protocol", choices=("upstream", "leakage-safe", "all-sources"), default="upstream")
    parser.add_argument("--epochs", type=float, default=5)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=5e-6)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    all_sources = args.protocol == "all-sources"
    data_dir = "data/processed_all" if all_sources else "data/processed"
    args.train = args.train or f"{data_dir}/train.csv"
    args.val = args.val or f"{data_dir}/val.csv"
    args.test = args.test or f"{data_dir}/test.csv"
    args.output = args.output or ("artifacts/phobert_all" if all_sources else "artifacts/phobert")
    args.metrics = args.metrics or ("artifacts/all_sources_metrics.json" if all_sources else "artifacts/metrics.json")
    args.data_report = args.data_report or ("artifacts/all_sources_report.json" if all_sources else "artifacts/data_report.json")
    report_path = Path(args.data_report)
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        actual_protocol = {"upstream-published-tiktok-splits": "upstream", "all-sources-grouped-split": "all-sources"}.get(report.get("protocol"), "leakage-safe")
        if actual_protocol != args.protocol:
            parser.error(f"Data report indicates {actual_protocol} data but --protocol is {args.protocol}; rerun prepare_data.py or select the matching protocol")
    for path in (args.train, args.val, args.test):
        if not Path(path).exists():
            raise SystemExit(f"Missing {path}; run python scripts/prepare_data.py")
    if not 2 <= args.max_length <= 256:
        parser.error("--max-length must be between 2 and 256 for PhoBERT")
    set_seed(args.seed)
    published_text = args.protocol in ("upstream", "all-sources")
    train_x, train_y = read_split(Path(args.train), published_text=published_text)
    val_x, val_y = read_split(Path(args.val), published_text=published_text)
    test_x, test_y = read_split(Path(args.test), published_text=published_text)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, use_fast=False)
    model = AutoModelForSequenceClassification.from_pretrained(args.base_model, num_labels=len(LABELS), id2label={i: label for i, label in enumerate(LABELS)}, label2id={label: i for i, label in enumerate(LABELS)})
    train_data = TextDataset(train_x, train_y, tokenizer, args.max_length, already_segmented=published_text)
    val_data = TextDataset(val_x, val_y, tokenizer, args.max_length, already_segmented=published_text)
    test_data = TextDataset(test_x, test_y, tokenizer, args.max_length, already_segmented=published_text)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    use_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    training_args = TrainingArguments(output_dir=str(output / "checkpoints"), num_train_epochs=args.epochs, per_device_train_batch_size=args.batch_size, per_device_eval_batch_size=args.batch_size, learning_rate=args.learning_rate, eval_strategy="epoch", save_strategy="epoch", load_best_model_at_end=True, metric_for_best_model="macro_f1", greater_is_better=True, save_total_limit=2, bf16=use_bf16, fp16=torch.cuda.is_available() and not use_bf16, tf32=torch.cuda.is_available(), seed=args.seed, report_to="none")

    def compute_metrics(result):
        predicted = np.argmax(result.predictions, axis=-1)
        return {"macro_f1": f1_score(result.label_ids, predicted, labels=list(range(len(LABELS))), average="macro", zero_division=0)}

    trainer = Trainer(model=model, args=training_args, train_dataset=train_data, eval_dataset=val_data, data_collator=DataCollatorWithPadding(tokenizer), compute_metrics=compute_metrics)
    trainer.train()
    val_metrics = evaluate(trainer, val_data)
    test_metrics = evaluate(trainer, test_data)
    trainer.save_model(str(output))
    tokenizer.save_pretrained(str(output))
    trained_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    metadata = {"model_version": "phobert-base-v2-finetuned-v1", "base_model": args.base_model, "positive_label": "phân biệt", "preprocessing_version": PREPROCESSING_VERSION, "segmentation": "published-vncorenlp" if published_text else "underthesea-word_tokenize-text", "protocol": args.protocol, "max_length": args.max_length, "trained_at": trained_at, "known_labels": list(LABELS)}
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    metrics = {**metadata, "validation": val_metrics, "test": test_metrics}
    metrics_path = Path(args.metrics)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Validation macro-F1: {val_metrics['macro_f1']:.4f}")
    print(f"Test macro-F1: {test_metrics['macro_f1']:.4f}")
    print(f"Saved model: {output}")
    print(f"Saved metrics: {metrics_path}")


if __name__ == "__main__":
    main()
