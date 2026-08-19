# Validation record

Ngày kiểm tra: 2026-08-20

Đã thực hiện:

- `python -m py_compile gphotos_short_video_cleaner.py`: đạt.
- `python -m unittest discover -s tests -v`: 18/18 ca đạt.
- Launcher Windows giữ đúng `--delete`: self-test báo `Chế độ xoá: BẬT`.
- Runtime dry-run trên tài khoản thật: 5.169 video, 2.062 ứng viên, 0 video thiếu thời lượng, dừng đúng tại `end-of-gallery` sau 740 vòng cuộn.
- Mô phỏng DOM bằng Chromium cho các trường hợp:
  - `0:03` được nhận khi ngưỡng là 4.
  - `0:04` bị loại.
  - Tile Photo có chuỗi giống thời lượng bị loại.
  - Tile Video không có badge bị bỏ qua.
  - Ưu tiên badge thời lượng ở góc dưới-phải thay vì chuỗi thời gian ở phía trên.
  - Nút “Chuyển vào thùng rác” tiếng Việt được nhận đúng.
  - Hộp thoại “Xoá vĩnh viễn” bị từ chối.
  - Nút xoá trùng/không rõ ràng làm tool dừng an toàn.

Người dùng đã xác nhận chế độ xoá chạy thành công trên tài khoản thật. Đây không phải kiểm chứng độc lập phía máy chủ; Google có thể thay đổi DOM nên vẫn phải chạy dry-run và thử `--limit 3` trước khi chạy toàn bộ.
