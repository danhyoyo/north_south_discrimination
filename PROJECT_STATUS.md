# Project status — SQLite edition

- Không phụ thuộc Kafka hoặc Docker.
- TikTok LIVE đưa comment vào worker PhoBERT nội bộ.
- Kết quả dự đoán và gift event được lưu trong `data/results/analysis.db`.
- SQLite WAL cho phép dashboard đọc realtime trong lúc collector ghi.
- Flask web app có trang tổng quan, feed realtime, phân tích và tra cứu/xuất CSV.
- Thống kê gồm nhãn, confidence, latency, timeline, top tài khoản và gift event.
- Dataset replay có thể dùng để demo khi không có tài khoản đang LIVE.
