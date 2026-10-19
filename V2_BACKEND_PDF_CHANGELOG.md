# Law & AI Academic Research — V2 Backend + PDF

**Phạm vi:** Chỉ xử lý hai hạng mục: (1) backend/tìm kiếm/quality ranking và (2) bộ tải PDF. Thiết kế lại giao diện, Zotero, AI summary và hệ thống nhiều tài khoản **chưa** nằm trong bản này.

## 1. Sửa backend

- Luồng Academic Search nạp **SCImago đã lưu trong SQLite**, không chỉ nạp từ CSV upload ở cùng lần tìm kiếm.
- Luồng Academic Search nạp **whitelist đã lưu trong SQLite** và giữ nguyên trạng thái `enabled`, alias, ISSN; không tự ghi đè chỉnh sửa bằng `research_profile.json` ở mỗi lần tìm kiếm.
- Với cơ sở dữ liệu mới, whitelist từ research profile được khởi tạo một lần bằng marker trong `keyword_presets`; xóa whitelist sau đó không bị tự thêm lại.
- Thời điểm bài báo được xuất bản **không còn bị dùng nhầm** làm năm của bảng SCImago. Mặc định chọn edition ranking mới nhất trong số dữ liệu nhập; chỉ dùng đúng edition năm được chỉ định khi có lựa chọn, với fallback đến bản *không ghi năm* và vẫn để `quartile_year=None`.
- Phân hạng đa dòng trùng ISSN/năm/subject nếu mâu thuẫn giữ `Unknown`, tránh nhập CSV bị lỗi ràng buộc.
- Khử trùng tiêu đề áp dụng cả trường hợp một bản ghi có DOI và một bản ghi thiếu DOI; không tự gộp khi hai DOI đã biết khác nhau hoặc tên tạp chí rõ ràng khác nhau.

## 2. Sửa bộ tải PDF

- Dùng HTTP streaming (chunk 64 KiB), tính SHA-256 dần, không nạp toàn bộ PDF vào RAM; giới hạn dung lượng cả theo header lẫn byte thực tế.
- Chặn `http://127.0.0.1`, private/special IP, credentials nhúng trong URL và cổng lạ; kiểm tra DNS trước khi kết nối thật và **kiểm tra mọi hop redirect trước khi truy cập**; giới hạn 5 redirects.
- Không sử dụng HTTP(S) proxy lấy từ biến môi trường cho downloader mặc định.
- Tạm ghi `.part`, dọn khi lỗi và chỉ thay file đích khi nhận được PDF có `%PDF-` hợp lệ.
- `Retry failed` **giữ nguyên các lần tải thành công** và thứ tự danh sách; ZIP không đánh mất các PDF đã tải trước đó.
- Lịch sử download tasks vẫn có thể đọc từ SQLite khi Streamlit session đã mất, retry mới cũng được lưu vào SQLite.
- Tên PDF theo `[năm]_[tác giả đầu]_[tiêu đề].pdf` khi có metadata, fallback chỉ dùng tiêu đề; xử lý tên Windows reserved.
- Chỉ chọn URL toàn văn Open Access hoặc repository hợp pháp, không tự động vượt paywall, CAPTCHA hay đăng nhập.

## 3. Kiểm thử thực hiện

- `pytest -q --ignore=tests/test_app_ui.py`: 52 passed (offline tests).
- `python -m compileall -q app clients config core models repositories services tests`: thành công.
- Streamlit UI tests **chưa chạy trong môi trường làm việc này** do không có `streamlit` cài sẵn; cần chạy `uv sync --extra dev` trên máy người dùng rồi `uv run pytest`.
- Chưa xác nhận hiệu quả tải PDF trên API công khai thực tế hoặc nhà xuất bản có giới hạn truy cập. Các test tải dùng MockTransport.

## 4. Bảo mật và dữ liệu

- **Không** bàn giao `.env`, token/API key, `.git` hay `.venv` trong gói ZIP. Tạo `.env` từ `.env.example` và tự điền khóa mới khi sử dụng.
- Bản bàn giao có thể kèm SQLite và các PDF tải thành công từ bản ZIP gốc để giữ dữ liệu. Dữ liệu người dùng nên được sao lưu trước khi thay phần mềm.
- Kiểm tra DNS trước kết nối giúp giảm SSRF nhưng **không giải quyết triệt để DNS rebinding**. Khi đưa lên Internet, dùng quy tắc firewall chặn private/metadata IP ở egress, chạy dưới tài khoản ít quyền, và phân quyền người dùng.

## 5. Khởi chạy (Windows, PowerShell)

```powershell
cd <duong-dan-thu-muc-v2>
uv sync --extra dev
Copy-Item .env.example .env
# Tùy chọn: cấu hình Unpaywall email trong .env để tăng nguồn OA hợp pháp
uv run pytest
uv run streamlit run app/main.py
```

Sau khi ứng dụng mở, vào **Journal Management** để import SCImago SJR CSV (hoặc dùng dữ liệu đã nhập trong SQLite), chỉnh whitelist rồi dùng **Academic Search**. Vào **Paper Library** để tải PDF hợp pháp; trạng thái và lịch sử hiển thị ở **Download Manager**.
