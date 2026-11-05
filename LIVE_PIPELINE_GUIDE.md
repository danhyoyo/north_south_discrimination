# Pipeline TikTok LIVE + SQLite

## Luồng dữ liệu

```text
TikTok LIVE
  ├─ CommentEvent → queue.Queue → PhoBERT → classified_comments
  └─ GiftEvent ───────────────────────────→ live_events

SQLite analysis.db → Flask /api/snapshot → web/live.html
```

Không có broker trung gian. `SQLiteClassifierWorker` giữ model trong RAM và xử
lý bình luận trên một thread riêng để callback TikTok không phải chạy inference
trực tiếp. Hàng đợi mặc định chứa tối đa 1.000 event.

SQLite bật `journal_mode=WAL`, `synchronous=NORMAL` và `busy_timeout=10000` để
collector ghi trong lúc dashboard đọc.

## Chạy

1. Ghi URL dạng `https://www.tiktok.com/@username/live` vào `.env`.
2. Chạy `python scripts/tiktok_live_collector.py`.
3. Ở terminal khác, chạy `python scripts/live_dashboard.py`.
4. Mở <http://127.0.0.1:8000>.

Trạng thái collector được ghi tại
`data/state/tiktok_live_status_<username>.json`. Kết quả được lưu tại
`data/results/analysis.db`.

## API

- `GET /api/health`: kiểm tra Flask.
- `GET /api/snapshot?limit=200`: trạng thái và các dự đoán mới nhất của LIVE
  đang cấu hình.

## Lưu ý

- TikTokLive là thư viện không chính thức và LIVE phải đang công khai.
- Nếu hàng đợi đầy, collector ghi trạng thái lỗi thay vì làm treo callback.
- SQLite phù hợp một máy và lưu lượng đồ án. Không dùng thiết kế này để phân
  tán nhiều máy hoặc nhiều worker ghi đồng thời.
- Dự đoán là kết quả thống kê của model, không phải kết luận pháp lý.
