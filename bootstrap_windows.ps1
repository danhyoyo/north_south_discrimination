$ErrorActionPreference = "Stop"

python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}

& .\.venv\Scripts\python.exe scripts\download_dataset.py
& .\.venv\Scripts\python.exe scripts\validate_dataset.py
& .\.venv\Scripts\python.exe scripts\prepare_data.py

Write-Host ""
Write-Host "Bootstrap + data preparation xong. Bước tiếp theo BẠN chạy training:" -ForegroundColor Green
Write-Host ".\.venv\Scripts\python.exe scripts\train_model.py"
