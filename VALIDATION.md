# Validation record

Ngày kiểm tra: 2026-08-19

Đã thực hiện:

- `python -m py_compile gphotos_short_video_cleaner.py`: đạt.
- `python -m unittest discover -s tests -v`: 14/14 ca đạt.
- Mô phỏng DOM bằng Chromium cho các trường hợp:
  - `0:03` được nhận khi ngưỡng là 4.
  - `0:04` bị loại.
  - Tile Photo có chuỗi giống thời lượng bị loại.
  - Tile Video không có badge bị bỏ qua.
  - Ưu tiên badge thời lượng ở góc dưới-phải thay vì chuỗi thời gian ở phía trên.
  - Nút “Chuyển vào thùng rác” tiếng Việt được nhận đúng.
  - Hộp thoại “Xoá vĩnh viễn” bị từ chối.
  - Nút xoá trùng/không rõ ràng làm tool dừng an toàn.

Chưa thực hiện xoá trên một tài khoản Google Photos thật vì môi trường kiểm tra không có phiên đăng nhập của người dùng. Google có thể thay đổi DOM; phải chạy dry-run và thử `--limit 3` trước khi chạy toàn bộ.
