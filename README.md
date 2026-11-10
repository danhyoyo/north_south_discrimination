# Phân loại bình luận TikTok LIVE theo vùng miền

Ứng dụng đọc bình luận và quà tặng từ một phiên TikTok LIVE, phân loại bình luận bằng PhoBERT, lưu vào SQLite và hiển thị trên dashboard Flask. Có thể nhập bình luận thủ công tại giao diện để dự đoán riêng, không cần kết nối TikTok.

## Thành phần được triển khai

- `scripts/tiktok_live_collector.py`: nhận sự kiện LIVE, đưa bình luận vào worker và ghi kết quả vào SQLite.
- `scripts/live_dashboard.py` và `web/`: dashboard, thống kê, tra cứu, xuất CSV và dự đoán thủ công tại `POST /api/predict`.
- `src/virdc_stream/`: tiền xử lý, suy luận PhoBERT, schema sự kiện và truy cập SQLite.
- `artifacts/phobert/`: model cuối cùng để suy luận, phiên bản `phobert_3class_20261110_170724`, fine-tune từ `vinai/phobert-base-v2`.
- `train_binary_phobert_colab.ipynb`: notebook huấn luyện trên Colab; dữ liệu, checkpoint và các lần thử nghiệm khác không nằm trong repository.

Model xuất bản ở `artifacts/phobert/` là bản xuất của checkpoint tốt nhất `checkpoint-3420` trong lần train nói trên. Thư mục `artifacts/training_runs/` chỉ nằm trên máy đã huấn luyện. `ModelService` cũng chấp nhận đường dẫn đến thư mục lần train đó và tự tìm checkpoint tốt nhất từ `trainer_state.json`.

## Cài đặt

Yêu cầu Python 3.10 trở lên và Git LFS. Trên Windows PowerShell:

```powershell
git clone https://github.com/danhyoyo/north_south_discrimination.git
cd north_south_discrimination
git lfs install
git lfs pull
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Sửa `.env` theo phiên LIVE cần theo dõi:

```dotenv
MODEL_PATH=artifacts/phobert
DATABASE_PATH=data/results/analysis.db
CLASSIFIER_QUEUE_SIZE=1000
TIKTOK_LIVE_URL=https://www.tiktok.com/@username/live
```

Nếu dùng chính thư mục huấn luyện trên máy hiện tại, đặt `MODEL_PATH=D:/Kafka_Web_Bac_Nam/sqlite_realtime/artifacts/training_runs/phobert_3class_20261110_170724`. Đường dẫn đó không có trên máy mới clone; dùng `artifacts/phobert` theo mặc định. Model phải có `metadata.json`, tokenizer và trọng số hợp lệ.

## Chạy

Mở hai terminal tại thư mục repository:

```powershell
# Terminal 1: nhận bình luận và phân loại
python .\scripts\tiktok_live_collector.py

# Terminal 2: dashboard
python .\scripts\live_dashboard.py
```

Mở <http://127.0.0.1:8000>. Trang `/live` hiển thị luồng bình luận, `/analytics` hiển thị thống kê, `/data` tra cứu và xuất CSV. Trang chủ có phần nhập bình luận để dự đoán thủ công. Dashboard vẫn mở được khi chưa có LIVE; collector cần một URL TikTok đang phát.

Có thể thử model độc lập:

```powershell
python .\scripts\smoke_predict.py --text "nam kì"
```

Để chia sẻ dashboard tạm thời, chạy `ngrok http 8000` ở terminal thứ ba sau khi Flask đã chạy. URL ngrok đưa dashboard ra internet; ứng dụng hiện chưa có xác thực.

## Huấn luyện trên Colab

Mở [train_binary_phobert_colab.ipynb](train_binary_phobert_colab.ipynb) trong Colab và làm theo các cell. Notebook giữ câu gốc và bổ sung biến thể bỏ dấu vào tập train. Dữ liệu đầu vào, checkpoint và model sinh ra khi huấn luyện không được commit. Sau khi huấn luyện, xuất model tốt nhất cùng tokenizer và metadata vào một thư mục dùng cho `MODEL_PATH`.

## Dữ liệu và API

SQLite mặc định ở `data/results/analysis.db`; dữ liệu và `.env` được giữ cục bộ. Các endpoint chính: `GET /api/snapshot`, `GET /api/comments`, `GET /api/analytics`, `GET /api/export.csv`, `POST /api/predict`, `GET /api/health`.

PhoBERT phân loại ba nhãn `khác`, `ủng hộ`, `phân biệt`. Kết quả dự đoán có thể sai, đặc biệt với bình luận ngắn hoặc thiếu ngữ cảnh.
