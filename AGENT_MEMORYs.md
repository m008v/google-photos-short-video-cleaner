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

## 2026-08-19 - Làm rõ và giữ chắc cờ chế độ xoá qua launcher

- Báo cáo runtime mới nhất quét đủ 5.169 video, tìm 2.062 ứng viên, không thiếu duration nhưng không tạo báo cáo xoá.
- Chụp `$args` vào `$cleanerArguments` ngay đầu PowerShell rồi dùng duy nhất biến này để kiểm tra và chuyển tiếp `--delete`.
- Launcher và Python đều in `Chế độ xoá: BẬT/TẮT`; chế độ BẬT nói rõ dry-run toàn bộ là bước bắt buộc trước khi hỏi `MOVE_TO_TRASH`.
- Tách nhánh kết thúc do tắt xoá khỏi nhánh không có ứng viên để người dùng không còn thấy tool im lặng sau dry-run.

## 2026-08-20 - Thêm CI/CD GitHub Actions

- Người dùng xác nhận luồng quét/xoá chạy thành công và yêu cầu push cùng CI/CD.
- Thêm workflow test trên Ubuntu/Windows với Python 3.10/3.14; chạy unit test, `py_compile` và self-test launcher Windows giữ cờ `--delete`.
- Pin action chính thức theo commit: `actions/checkout` v7.0.1 và `actions/setup-python` v7.0.0; CI chỉ có quyền `contents: read`.
- Tag `vX.Y.Z` sau khi test đạt sẽ đóng gói ZIP, tạo SHA-256 và tạo/cập nhật GitHub Release bằng `gh` với `contents: write` chỉ ở job release.
- Thêm Dependabot cập nhật GitHub Actions hàng tuần và badge CI/CD trong README.

## 2026-08-24 — Viết lại README cho người dùng cơ bản

### Mục tiêu

- Viết lại hướng dẫn sử dụng theo workflow Windows dễ làm theo và push lên GitHub.

### Đã thực hiện

- Viết lại `README.md` theo thứ tự tải ZIP, cài đặt, quét thử, xoá thử 3 video và xoá toàn bộ.
- Thêm bảng tiêu chí thời lượng, cảnh báo đồng bộ, xử lý lỗi thường gặp, quyền riêng tư và phần nâng cao có thể thu gọn.
- Giữ badge CI/CD, lệnh kiểm thử và hướng dẫn phát hành cho maintainer ở cuối tài liệu.

### Quyết định kỹ thuật

- Ưu tiên các file `.bat` làm giao diện chính; lệnh Python được chuyển vào phần nâng cao.
- Không hướng dẫn bỏ qua dry-run hoặc xác nhận `MOVE_TO_TRASH` vì đây là các lớp bảo vệ dữ liệu.

### Kiểm tra

- Đối chiếu hướng dẫn với các launcher Windows, tham số CLI và workflow CI/CD hiện tại.
- Kiểm tra Markdown, UTF-8, mojibake và các lệnh kiểm thử trước khi commit.

### Việc còn lại

- Chưa có ảnh chụp màn hình minh hoạ; có thể bổ sung sau nếu giao diện Google Photos ổn định đủ lâu.

## 2026-08-24 — Nâng lô xoá mặc định lên 100 video

### Mục tiêu

- Chọn tối đa 100 video trong mỗi lần chuyển vào Thùng rác thay vì 25.

### Đã thực hiện

- Đổi giá trị mặc định của `--batch-size` từ 25 lên 100.
- Cập nhật README và thêm unit test khóa giá trị mặc định.
- Giữ launcher xoá thử ở `--limit 3 --batch-size 3` để bước kiểm tra ban đầu không đổi.

### Quyết định kỹ thuật

- Không thay đổi giới hạn tối đa 100 hoặc các kiểm tra số lượng mục đã chọn trước khi xoá.
- Launcher xoá toàn bộ tiếp tục dùng giá trị mặc định từ CLI, tránh lặp cấu hình ở nhiều file.

### Kiểm tra

- Chạy unit test, `py_compile`, launcher self-test, kiểm tra diff và mojibake trước khi commit.

### Việc còn lại

- Cần kiểm chứng một lô 100 video trên giao diện Google Photos thật vì DOM và giới hạn phía Google có thể thay đổi.
