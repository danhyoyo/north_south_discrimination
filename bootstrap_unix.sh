#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
fi

.venv/bin/python scripts/download_dataset.py
.venv/bin/python scripts/validate_dataset.py
.venv/bin/python scripts/prepare_data.py

echo
echo "Bootstrap + data preparation xong. Bước tiếp theo BẠN chạy training:"
echo ".venv/bin/python scripts/train_model.py"
