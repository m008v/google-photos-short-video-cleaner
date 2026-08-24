# Google Photos Short Video Cleaner

[![CI/CD](https://github.com/m008v/google-photos-short-video-cleaner/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/m008v/google-photos-short-video-cleaner/actions/workflows/ci-cd.yml)

Công cụ dành cho Windows giúp tìm các video có thời lượng hiển thị **ngắn hơn 4 giây**
trong Google Photos và chuyển chúng vào **Thùng rác** sau khi bạn xác nhận.

> Công cụ không xoá vĩnh viễn, không lưu mật khẩu Google và mặc định chỉ quét để bạn
> kiểm tra trước.

## Dành cho ai?

README này dành cho người dùng Windows cơ bản. Bạn chỉ cần biết cách tải ZIP, giải nén
và nhấp đúp file `.bat`; không cần biết Python hay Selenium hoạt động thế nào.

## Chuẩn bị

Máy tính cần có:

- Windows 10 hoặc Windows 11.
- [Google Chrome](https://www.google.com/chrome/).
- [Python 3.10 trở lên](https://www.python.org/downloads/windows/). Khi cài Python,
  nhớ chọn **Add Python to PATH**.
- Kết nối Internet ổn định.

Bạn không cần tự tải ChromeDriver.

## Cài đặt lần đầu

### Bước 1: Tải và giải nén

1. Mở trang GitHub của dự án.
2. Chọn **Code → Download ZIP**.
3. Giải nén ZIP vào một thư mục dễ tìm, ví dụ `Downloads` hoặc `Desktop`.
4. Không chạy trực tiếp các file khi chúng vẫn còn nằm bên trong ZIP.

### Bước 2: Cài công cụ

Trong thư mục vừa giải nén, nhấp đúp:

```text
setup_windows.bat
```

File này sẽ:

1. Kiểm tra Python.
2. Tạo môi trường riêng `.venv`.
3. Cài Selenium.
4. Chạy bộ kiểm thử để phát hiện lỗi cài đặt.

Khi terminal báo cài đặt và kiểm thử hoàn tất, bạn có thể bắt đầu quét.

## Cách dùng an toàn

Nên thực hiện đúng thứ tự sau:

```text
Quét thử → xem báo cáo → xoá thử 3 video → kiểm tra Thùng rác → xoá toàn bộ
```

Đừng nhảy thẳng đến xoá toàn bộ. Nút bấm nhanh không biến một quyết định liều thành
một quyết định thông minh.

## 1. Quét thử, không xoá

Nhấp đúp:

```text
run_scan_windows.bat
```

Lần chạy đầu tiên:

1. Một cửa sổ Chrome riêng sẽ mở.
2. Đăng nhập Google trong cửa sổ Chrome đó.
3. Chờ Google Photos hiển thị bình thường.
4. Quay lại cửa sổ terminal và nhấn Enter.
5. Giữ cửa sổ Chrome mở trong lúc công cụ tự cuộn và quét.

Terminal phải hiển thị:

```text
CHẾ ĐỘ XOÁ: TẮT
```

Ở chế độ này, công cụ không chọn và không xoá video.

Kết quả được lưu trong thư mục:

```text
reports
```

Bạn nên mở file CSV mới nhất để kiểm tra số lượng và danh sách video được nhận diện.

## 2. Xoá thử tối đa 3 video

Sau khi kiểm tra báo cáo quét, nhấp đúp:

```text
run_delete_test3_windows.bat
```

Terminal phải hiển thị:

```text
Chế độ xoá: BẬT
```

Công cụ vẫn quét toàn bộ thư viện trước. Đây là bước an toàn bắt buộc, không phải công
cụ bị kẹt ở dry-run.

Khi quá trình quét kết thúc, nhập chính xác:

```text
MOVE_TO_TRASH
```

Công cụ chỉ chuyển tối đa 3 video phù hợp vào Thùng rác. Hãy mở Thùng rác Google
Photos và kiểm tra đúng video trước khi tiếp tục.

## 3. Xoá toàn bộ video phù hợp

Chỉ thực hiện sau khi phiên thử 3 video cho kết quả đúng.

Nhấp đúp:

```text
run_delete_windows.bat
```

Công cụ sẽ:

1. Quét lại toàn bộ thư viện.
2. Hiển thị kết quả dry-run.
3. Yêu cầu nhập `MOVE_TO_TRASH`.
4. Chuyển các video phù hợp vào Thùng rác theo từng lô.

Nếu không nhập đúng `MOVE_TO_TRASH`, công cụ sẽ dừng mà không xoá.

## Hiểu đúng tiêu chí “ngắn hơn 4 giây”

Công cụ đọc thời lượng đang hiển thị trên thumbnail Google Photos:

| Thời lượng hiển thị | Kết quả |
|---|---|
| `0:00` đến `0:03` | Được nhận diện |
| `0:04` trở lên | Bỏ qua |
| Không có nhãn thời lượng | Bỏ qua |

Phép so sánh là `< 4`, không phải `≤ 4`.

## Những điều cần biết trước khi xoá

- Thao tác trong Google Photos có thể đồng bộ sang điện thoại và thiết bị đang bật sao
  lưu.
- Công cụ chỉ chuyển video vào Thùng rác và từ chối nút **Xoá vĩnh viễn**.
- Motion Photo hoặc Live Photo có thể được nhận nếu Google Photos hiển thị chúng như
  Video và có thời lượng dưới ngưỡng.
- Báo cáo CSV/JSON có thể chứa nhãn và URL nội bộ của ảnh/video. Không đăng công khai
  thư mục `reports`.
- Google có thể thay đổi giao diện bất kỳ lúc nào. Luôn quét thử và thử 3 video trước.

## Xử lý lỗi thường gặp

### Google báo “Trình duyệt hoặc ứng dụng này có thể không an toàn”

Đóng cửa sổ Chrome riêng của công cụ rồi chạy lại file `.bat`. Công cụ mở Chrome thường
để bạn đăng nhập trước, sau đó Selenium mới kết nối vào phiên đã đăng nhập.

Không dùng profile Chrome cá nhân đang mở để chạy remote debugging.

### Terminal chỉ hiện “Bắt đầu dry-run” khi đang chạy chế độ xoá

Đây là hành vi đúng. Chế độ xoá luôn dry-run toàn bộ trước khi hỏi `MOVE_TO_TRASH`.
Với thư viện có hàng nghìn video, quá trình này có thể mất nhiều phút.

Kiểm tra phần đầu terminal:

```text
Chế độ xoá: BẬT
```

Nếu terminal hiển thị `TẮT`, bạn đã chạy nhầm `run_scan_windows.bat`.

### File `.bat` không chạy hoặc báo không tìm thấy đường dẫn

- Giải nén toàn bộ ZIP trước khi chạy.
- Không gõ riêng `.bat` trong terminal.
- Mở đúng thư mục dự án rồi nhấp đúp tên file đầy đủ.
- Chạy lại `setup_windows.bat` nếu thư mục `.venv` chưa tồn tại.

### Công cụ không nhận diện video hoặc không tự cuộn

- Chờ trang Video tải xong trước khi nhấn Enter.
- Không đóng Chrome trong lúc quét.
- Kiểm tra kết nối Internet.
- Đóng Chrome riêng của công cụ rồi chạy lại để dùng phiên mới.
- Nếu Google vừa thay đổi giao diện, gửi log terminal và báo cáo JSON để kiểm tra.

### Muốn kiểm tra launcher mà không quét

Mở terminal trong thư mục dự án và chạy:

```bat
run_with_browser_windows.bat --launcher-self-test
```

Kết quả thành công phải cho biết Python, Chrome và chế độ chuyển tiếp tham số đều sẵn
sàng.

## Dữ liệu và quyền riêng tư

- Mật khẩu được nhập trực tiếp trên trang Google; công cụ không đọc hoặc ghi mật khẩu.
- Phiên đăng nhập được giữ trong profile riêng tại:

```text
%USERPROFILE%\.gphotos-short-video-cleaner\chrome-login-profile
```

- Cổng debug chỉ lắng nghe tại `127.0.0.1`.
- Đóng cửa sổ Chrome riêng sau khi công cụ hoàn tất để tắt cổng debug.
- Công cụ không gọi API nội bộ để tải nội dung ảnh hoặc video.

<details>
<summary><strong>Dành cho người dùng nâng cao</strong></summary>

### Cài đặt thủ công

```bash
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Quét

```bash
.venv\Scripts\python.exe gphotos_short_video_cleaner.py --threshold 4
```

### Xoá thử 3 video

```bash
.venv\Scripts\python.exe gphotos_short_video_cleaner.py --threshold 4 --delete --limit 3 --batch-size 3
```

### Xoá toàn bộ video phù hợp

```bash
.venv\Scripts\python.exe gphotos_short_video_cleaner.py --threshold 4 --delete
```

### Tham số chính

```text
--threshold 4          Ngưỡng giây, so sánh nghiêm ngặt <
--delete               Bật chế độ chuyển video vào Thùng rác sau dry-run
--limit 3              Giới hạn tổng số video xử lý; 0 là không giới hạn
--batch-size 25        Số video mỗi lô, từ 1 đến 100
--output-dir reports   Thư mục lưu báo cáo
--scroll-settle 0.45   Thời gian chờ lazy-load sau mỗi lần cuộn
--action-timeout 15    Timeout cho nút xoá và hộp thoại
--log-level INFO       Mức log: DEBUG, INFO, WARNING hoặc ERROR
```

Không nên dùng `--confirm MOVE_TO_TRASH` nếu chưa tự kiểm tra dry-run trong cùng điều
kiện, vì tham số này bỏ qua bước nhập xác nhận tương tác.

</details>

## Kiểm tra và CI/CD

Chạy kiểm thử cục bộ:

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m py_compile gphotos_short_video_cleaner.py
```

GitHub Actions kiểm tra trên Ubuntu/Windows với Python 3.10 và 3.14. Khi push tag đúng
dạng `vX.Y.Z`, workflow tạo GitHub Release gồm file ZIP và checksum SHA-256.

Ví dụ:

```bash
git tag v1.0.0
git push origin v1.0.0
```

## Giấy phép và cảnh báo

Dự án chưa khai báo file giấy phép riêng. Việc sử dụng công cụ là trách nhiệm của bạn;
hãy kiểm tra báo cáo và cấu hình đồng bộ Google Photos trước khi xác nhận xoá.
