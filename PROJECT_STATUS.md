# Project status — SQLite edition

- Không phụ thuộc Kafka hoặc Docker.
- TikTok LIVE và TikTok video đều đưa comment vào worker PhoBERT nội bộ.
- Kết quả dự đoán và gift event được lưu trong `data/results/analysis.db`.
- SQLite WAL cho phép dashboard đọc realtime trong lúc collector ghi.
- Flask dashboard lọc đúng tài khoản LIVE và tự cập nhật mỗi 2 giây.
- Dataset replay có thể dùng để demo khi không có tài khoản đang LIVE.
