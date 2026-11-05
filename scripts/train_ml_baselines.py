from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.naive_bayes import MultinomialNB


LABELS = ("khác", "ủng hộ", "phân biệt")


def read_split(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if not {"sentence", "label"}.issubset(frame.columns):
        raise ValueError(f"{path}: expected sentence and label columns")
    if frame[["sentence", "label"]].isna().any().any():
        raise ValueError(f"{path}: contains missing sentence or label")
    invalid = set(frame["label"]) - set(LABELS)
    if invalid:
        raise ValueError(f"{path}: invalid labels {sorted(invalid)}")
    return frame


def evaluate(model, features, labels) -> dict:
    predicted = model.predict(features)
    return {
        "rows": len(labels),
        "accuracy": float(accuracy_score(labels, predicted)),
        "macro_f1": float(f1_score(labels, predicted, labels=LABELS, average="macro", zero_division=0)),
        "labels": list(LABELS),
        "classification_report": classification_report(
            labels, predicted, labels=LABELS, output_dict=True, zero_division=0
        ),
        "confusion_matrix": confusion_matrix(labels, predicted, labels=LABELS).tolist(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train CountVectorizer ViRDC machine-learning baselines")
    parser.add_argument("--data-dir", default="data/processed_all")
    parser.add_argument("--output-dir", default="artifacts/ml_all_sources")
    parser.add_argument("--metrics", default="artifacts/ml_all_sources_metrics.json")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    splits = {name: read_split(data_dir / f"{name}.csv") for name in ("train", "val", "test")}
    texts = {name: set(frame["sentence"]) for name, frame in splits.items()}
    overlaps = {
        f"{a}_{b}": len(texts[a] & texts[b])
        for a, b in (("train", "val"), ("train", "test"), ("val", "test"))
    }
    print("Cross-split unique-text overlap:", overlaps)

    vectorizer = CountVectorizer()
    features = {"train": vectorizer.fit_transform(splits["train"]["sentence"])}
    for name in ("val", "test"):
        features[name] = vectorizer.transform(splits[name]["sentence"])
    print(f"Train rows: {len(splits['train']):,}; vocabulary: {len(vectorizer.vocabulary_):,}")

    models = {
        "random_forest": RandomForestClassifier(
            n_estimators=400, criterion="entropy", random_state=42, n_jobs=-1
        ),
        "multinomial_logistic_regression": LogisticRegression(
            solver="saga", max_iter=5000, random_state=42
        ),
        "multinomial_naive_bayes": MultinomialNB(alpha=1.0),
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {
        "trained_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data_dir": str(data_dir),
        "vectorizer": "CountVectorizer(defaults)",
        "solver_note": "Multinomial Logistic Regression uses saga because lbfgs crashes in the local Windows SciPy build.",
        "rows": {name: len(frame) for name, frame in splits.items()},
        "cross_split_unique_text_overlap": overlaps,
        "models": {},
    }
    for name, model in models.items():
        print(f"Training {name} ...")
        model.fit(features["train"], splits["train"]["label"])
        val = evaluate(model, features["val"], splits["val"]["label"])
        test = evaluate(model, features["test"], splits["test"]["label"])
        model_path = output_dir / f"{name}.joblib"
        joblib.dump({"vectorizer": vectorizer, "model": model, "labels": LABELS}, model_path)
        results["models"][name] = {"artifact": str(model_path), "validation": val, "test": test}
        print(f"  val F1-macro={val['macro_f1']:.4f}; test accuracy={test['accuracy']:.4f}; test F1-macro={test['macro_f1']:.4f}")

    metrics_path = Path(args.metrics)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved metrics: {metrics_path}")


if __name__ == "__main__":
    main()
