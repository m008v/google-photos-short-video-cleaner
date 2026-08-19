# Google Photos Short Video Cleaner (Selenium + Python)

Tool quét trang **Video** của Google Photos và, sau khi được xác nhận rõ ràng, chuyển các video có badge thời lượng **ngắn hơn 4 giây** vào **Thùng rác**.

## Cơ chế an toàn

- Mặc định chỉ **dry-run**: không chọn, không xoá; xuất CSV và JSON để kiểm tra trước.
- Chỉ nhận tile được Google Photos phân loại là **Video** và có badge thời lượng dạng `m:ss` hoặc `h:mm:ss`.
- So sánh nghiêm ngặt `< 4`: badge `0:03` được nhận; `0:04` không được nhận.
- Chế độ xoá chỉ dùng **allow-list đúng từ dry-run vừa hoàn tất**; video mới xuất hiện sau bước xác nhận không tự động được thêm.
- Tile chỉ có `aria-label` nhưng không có URL/ID/ảnh làm định danh sẽ được ghi vào báo cáo nhưng không được xoá.
- Chặn thao tác khi URL hiện tại là Thùng rác, album, trang chia sẻ hoặc không thuộc `photos.google.com`.
- Chặn thao tác nếu trên trang đã có một hộp thoại khác.
- Xoá theo lô mặc định 25 mục. Trước mỗi lô, bộ đếm mục chọn của Google Photos phải khớp chính xác số mục tool theo dõi.
- Chỉ nhấp nút xoá/xác nhận khi nhận diện được duy nhất bằng selector và nhãn truy cập.
- Nếu hộp thoại yêu cầu **Xoá vĩnh viễn**, tool dừng và không nhấp.
- Tool không dọn sạch Thùng rác và không lưu mật khẩu Google; đăng nhập được thực hiện thủ công trong Chrome.

> Google Photos là ứng dụng web động. Google có thể thay đổi DOM bất kỳ lúc nào. Luôn chạy dry-run, mở CSV kiểm tra, rồi thử với `--limit 3` trước.

## Yêu cầu

- Python 3.10+
- Google Chrome hoặc Chromium
- Kết nối Internet

Selenium 4 sử dụng Selenium Manager để tự tìm hoặc tải ChromeDriver trong phần lớn môi trường.

## Cài đặt

### Windows nhanh

Giải nén ZIP rồi chạy:

```bat
setup_windows.bat
```

Script tạo `.venv`, cài Selenium và chạy 14 kiểm thử lõi.

### Thủ công

```bash
python -m venv .venv
```

Windows:

```bat
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Cài dependency:

```bash
python -m pip install -r requirements.txt
```

## Chạy dry-run

```bash
python gphotos_short_video_cleaner.py --threshold 4
```

Chrome mở bằng một profile riêng. Đăng nhập thủ công, bảo đảm đang ở **Google Photos > Tìm kiếm > Video**, bỏ chọn mọi mục đang được chọn, rồi nhấn Enter trong terminal. Báo cáo nằm trong thư mục `reports/`.

Windows có thể chạy trực tiếp:

```bat
run_scan_windows.bat
```

## Thử xoá 3 video trước

```bash
python gphotos_short_video_cleaner.py --threshold 4 --delete --limit 3 --batch-size 3
```

Windows:

```bat
run_delete_test3_windows.bat
```

Tool luôn dry-run trước, sau đó hiển thị số lượng và yêu cầu nhập chính xác:

```text
MOVE_TO_TRASH
```

## Chuyển toàn bộ video khớp vào Thùng rác

Sau khi kiểm tra dry-run và phiên thử 3 mục:

```bash
python gphotos_short_video_cleaner.py --threshold 4 --delete
```

Windows:

```bat
run_delete_windows.bat
```

### Xác nhận không tương tác

Chỉ dùng khi đã tự kiểm tra dry-run trong cùng điều kiện:

```bash
python gphotos_short_video_cleaner.py --threshold 4 --delete --confirm MOVE_TO_TRASH
```

## Gắn vào Chrome đã mở sẵn

Dùng khi Google không cho đăng nhập trong cửa sổ WebDriver. Phải mở Chrome bằng **profile riêng**, không dùng profile Chrome mặc định đang chạy.

Windows, ví dụ:

```bat
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%USERPROFILE%\gphotos-debug-profile"
```

Sau khi đăng nhập:

```bash
python gphotos_short_video_cleaner.py --debugger-address 127.0.0.1:9222 --no-ready-prompt
```

Tool vẫn điều hướng tới trang Video mặc định. Khi gắn vào Chrome có sẵn, tool không tự đóng Chrome.

## Tham số chính

```text
--threshold 4          Ngưỡng; dùng phép so sánh <
--delete               Cho phép chuyển vào Thùng rác sau dry-run
--limit 3              Giới hạn tổng số mục xoá trong phiên
--batch-size 25        Kích thước lô, 1..100
--profile-dir PATH     Profile Chrome riêng để giữ phiên đăng nhập
--output-dir reports   Thư mục báo cáo
--scroll-settle 0.45   Tăng nếu mạng chậm hoặc lazy-load không kịp
--action-timeout 15    Timeout nút xoá và hộp thoại
--language vi-VN       Yêu cầu Chrome dùng giao diện tiếng Việt
--close-browser        Đóng Chrome ngay khi hoàn tất
```

## Giới hạn quan trọng

1. Tool dựa vào **thời lượng hiển thị trên thumbnail**, không đọc thời lượng mili-giây của tệp gốc. Video 3.x giây nhưng Google làm tròn badge thành `0:04` sẽ được bỏ qua.
2. Video không có badge hoặc không nhận diện chắc chắn là Video sẽ bị bỏ qua.
3. Motion Photo/Live Photo nếu Google Photos phân loại là Video và hiển thị badge dưới ngưỡng có thể được chọn như một mục Video hoàn chỉnh.
4. Các selector xoá được tối ưu cho giao diện tiếng Việt và tiếng Anh. Với ngôn ngữ khác, dry-run vẫn có thể hoạt động nhưng chế độ xoá có thể dừng an toàn vì không nhận diện được nút.
5. Báo cáo CSV/JSON có thể chứa nhãn và URL nội bộ của ảnh/video. Không đăng công khai các file trong `reports/`.
6. Một dòng `moved_to_trash` trong báo cáo xoá nghĩa là tool đã nhấp xác nhận và bộ đếm mục chọn của giao diện trở về 0; tool không đăng nhập lại Thùng rác để kiểm chứng độc lập phía máy chủ.
7. Xoá trong Google Photos có thể đồng bộ sang thiết bị đang cài Google Photos và bật sao lưu. Kiểm tra cấu hình sao lưu trước.

## Kiểm tra mã nguồn

```bash
python -m unittest discover -s tests -v
python -m py_compile gphotos_short_video_cleaner.py
```
