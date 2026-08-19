# AGENT MEMORY

## 2026-08-19 - Khắc phục Google chặn đăng nhập trong Chrome WebDriver

- Nguyên nhân: Google có thể từ chối đăng nhập khi phát hiện Chrome đang được điều khiển bởi Selenium/WebDriver.
- Thêm `run_with_browser_windows.bat` để mở Chrome thường với profile riêng và cổng debug chỉ lắng nghe tại `127.0.0.1`; người dùng đăng nhập xong thì Selenium mới gắn vào phiên Chrome.
- Chuyển `run_scan_windows.bat`, `run_delete_test3_windows.bat` và `run_delete_windows.bat` sang launcher an toàn này; giữ nguyên dry-run, giới hạn xoá thử và bước xác nhận `MOVE_TO_TRASH`.
- Cập nhật README với workflow Windows, cách xử lý cảnh báo trình duyệt không an toàn và hướng dẫn gắn Chrome thủ công.
- Xác minh: 14/14 unit test đạt, `py_compile` đạt, `git diff --check` đạt và không phát hiện mojibake trong các tệp nguồn UTF-8.

## 2026-08-19 - Sửa launcher Windows bị cmd.exe cắt vỡ UTF-8

- Triệu chứng: `cmd.exe` coi các mảnh tiếng Việt và `$r.webSocketDebuggerUrl)` là lệnh riêng khi chạy batch UTF-8 dùng LF-only.
- Chuyển toàn bộ logic launcher sang `run_with_browser_windows.ps1`; `run_with_browser_windows.bat` chỉ còn lệnh ASCII gọi PowerShell.
- Thêm `.gitattributes` để bắt buộc CRLF cho `.bat`/`.ps1`, đồng thời giữ các wrapper `.bat` ở dạng ASCII.
- Thêm `--launcher-self-test` để kiểm tra đường gọi thật từ `cmd.exe` tới PowerShell mà không mở Chrome hoặc khởi chạy quét.

## 2026-08-19 - Sửa auto-scroll và nhận dạng video trên DOM Google Photos mới

- Bằng chứng runtime trước sửa: DOM có 68 checkbox, 61 tile Video nhưng tool đọc 0 thời lượng; vùng cuộn bị nhận nhầm là `document.scrollingElement` với `height=client=876`.
- DOM hiện tại đặt checkbox bên trong card `.rtIMgb`; badge thời lượng và anchor `/photo/` nằm ở card cha, không nằm trong khung 32x32 của checkbox.
- Tìm vùng cuộn bằng cách lần từ checkbox lên tổ tiên scrollable; runtime nhận đúng container cao 25.519 px và cuộn từ 0 lên 446 px.
- Nhận dạng card cha để đọc 61/61 badge thời lượng, 31 ứng viên dưới 4 giây trong vùng render và 61/61 định danh `photo-href`.
- Khi tile ảo ban đầu chưa hiện badge, quan sát có thời lượng về sau sẽ thay thế dữ liệu cũ và loại mục khỏi báo cáo thiếu thời lượng.
- Giữ nguyên trang hiện tại khi gắn Chrome, dùng link Video hiện hành của UI nếu cần và thêm cờ chống throttling nền cho Chrome profile riêng.
