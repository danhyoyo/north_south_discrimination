from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from virdc_stream.config import settings  # noqa: E402
from virdc_stream.database import fetch_comments, fetch_summary  # noqa: E402


st.set_page_config(page_title="ViRDC Streaming Dashboard", layout="wide")
st.title("ViRDC realtime discrimination dashboard")
st.caption("Dữ liệu được pipeline realtime ghi trực tiếp vào SQLite.")

path = settings.database_path
if not path.exists():
    st.info(f"Chưa có kết quả tại {path}. Hãy chạy collector hoặc replay_producer trước.")
    st.stop()

rows, _ = fetch_comments(path, limit=10000)
summary = fetch_summary(path)

if not rows:
    st.info("Cơ sở dữ liệu chưa có kết quả phân loại.")
    st.stop()

flat = []
for row in rows:
    prediction = row.get("prediction", {})
    flat.append(
        {
            "classified_at": row.get("classified_at"),
            "source": row.get("source"),
            "text": row.get("text"),
            "label": prediction.get("label"),
            "score": prediction.get("score"),
            "is_discrimination": prediction.get("is_discrimination"),
            "latency_ms": row.get("latency_ms"),
        }
    )

df = pd.DataFrame(flat)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Comments", summary["total"])
c2.metric("Phân biệt", summary["discrimination"])
rate = summary["discrimination"] / summary["total"] * 100 if summary["total"] else 0.0
c3.metric("Tỷ lệ phân biệt", f"{rate:.1f}%")
latency = summary["average_latency_ms"]
c4.metric("Latency trung bình", f"{latency:.1f} ms" if pd.notna(latency) else "n/a")

st.subheader("Phân bố nhãn")
st.bar_chart(df["label"].value_counts())

st.subheader("Kết quả gần nhất")
st.dataframe(df.iloc[::-1].head(100), use_container_width=True)
