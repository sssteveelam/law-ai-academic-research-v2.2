# V2.1 – Sửa luồng tìm và tải PDF cho thư viện cũ

## Chẩn đoán thực tế từ `data/research.db` trong ZIP của người dùng

- `papers`: **102** bản ghi.
- Bản ghi có `pdf_url`: **0**; bản ghi có `oa_locations` khác `[]`: **0**.
- Lịch sử ban đầu: 5 lượt `DOWNLOADED`, 131 lượt `ACCESS_RESTRICTED`, 14 lượt `FAILED`, 1 lượt `INVALID_PDF`.
- Nhiều bài chỉ có DOI hoặc link trang nhà xuất bản; bản V2 không tra OpenAlex theo DOI trước khi tải. Vì vậy chọn bài từ thư viện cũ thường không có URL PDF để tải.
- Bản V2 trước chỉ có nút tải ZIP ở Download Manager của phiên hiện tại; file đã được lưu trên ổ đĩa vẫn có thể không được tải về trình duyệt.

## Bản sửa V2.1

1. `OpenAlexClient.lookup_dois()` tìm lại metadata theo **DOI chính xác**, truy vấn theo lô tối đa 50 DOI/lượt và dùng cache hiện tại. OpenAlex key không bắt buộc ở mọi trường hợp, nhưng giới hạn API và truy cập mạng vẫn có thể ảnh hưởng.
2. `FullTextResolver.prime()` bổ sung PDF Open Access từ OpenAlex cho các bản ghi cũ chưa có URL, và vẫn thử Unpaywall nếu đã cung cấp contact email. Không suy diễn link trang giới thiệu thành PDF và không vượt paywall.
3. Giảm link giả: OpenAlex chỉ lấy PDF ở `best_oa_location` hoặc `primary_location` có `is_oa=true`, không coi PDF publisher đóng là bản Open Access.
4. Khi trả HTTP 401/403: phân loại `ACCESS_RESTRICTED`, vẫn tiếp tục nguồn thay thế; API lỗi được ghi trong cột `Error`, không làm hỏng cả đợt tải.
5. Downloader chấp nhận file PDF có Content-Type bị ghi sai *nếu* bytes thật bắt đầu bằng `%PDF-`; trả HTML hoặc PDF giả vẫn bị chặn. Tải theo chunk, giới hạn kích thước, kiểm tra URL/redirect, dọn file `.part`. Báo rõ lỗi mạng / quyền ghi.
6. `Paper Library` có nút **Tải các PDF về máy của tôi (ZIP)** và nút tải PDF riêng ngay sau khi đợt tải kết thúc. `Download Manager` vẫn có nút ZIP của phiên hiện tại.
7. `Download Manager` hiển thị các PDF còn tồn tại từ lịch sử SQLite, kể cả sau khi trình duyệt/phiên Streamlit bị khởi động lại, với kiểm soát chỉ đọc file dưới download directory.
8. Thêm `scripts/diagnose_pdf.py` để người dùng thử kiểm tra một DOI trực tiếp trên máy mình.
9. Thêm lựa chọn `LAW_RESEARCH_DOWNLOAD_USE_SYSTEM_PROXY` nếu môi trường Windows buộc phải kết nối qua proxy; mặc định **false** vì an toàn. Khi bật phải cấu hình mạng chặn truy cập private egress.

## Chạy trên Windows

1. Đóng ứng dụng V2 đang chạy.
2. Giải nén bản ZIP V2.1 vào **thư mục mới** (đừng trộn source với V2 cũ); V2.1 có bản sao dữ liệu SQLite và 5 PDF từ ZIP cũ.
3. Mở PowerShell tại thư mục `law-ai-academic-research-v2.1`:

```powershell
uv sync --extra dev
Copy-Item .env.example .env
# Chỉnh .env nếu có key/email. Đặc biệt khuyến nghị LAW_RESEARCH_UNPAYWALL_EMAIL=you@example.com
uv run pytest
uv run streamlit run app/main.py
```

4. Vào **Paper Library → Select all visible (hoặc tích bài cần tải) → Download selected PDFs**. Sau khi chạy, xem bảng `Status/Error`, và dùng nút **Tải các PDF về máy của tôi (ZIP)**.
5. Vào **Download Manager** để tải lại file đã tải trước đó, hoặc **Retry failed** nếu muốn thử nguồn mới.

### Lệnh chẩn đoán một DOI

```powershell
uv run python scripts/diagnose_pdf.py 10.1371/journal.pone.0266781
```

Có thể đổi sang DOI của bài mà bạn cần. Script cho biết rõ `DOWNLOADED`, `ACCESS_RESTRICTED`, hoặc `FAILED`, lý do, thư mục đã ghi.

### Khi không tải được

- **`ACCESS_RESTRICTED` + “No lawful OA PDF”**: nguồn metadata chưa có bản PDF miễn phí. Có thể chỉ có landing page; cần tìm bản Open Access hợp pháp hoặc sử dụng quyền truy cập của cơ quan.
- **`OpenAlex HTTP 401/403/429`**: API không cho truy cập hoặc bị giới hạn. Kiểm tra cấu hình API key và mạng.
- **`network error`**: kiểm tra firewall/proxy/DNS; chỉ bật system proxy trong môi trường tin cậy có mạng egress bảo vệ.
- **`HTTP 403` đối với URL PDF**: máy chủ từ chối tải; không thể suy ra phần mềm chắc chắn đã hỏng. Dùng nguồn Open Access khác.
- **`unable to save PDF`**: kiểm tra quyền ghi thư mục `data/downloads`.
- **`INVALID_PDF`**: máy chủ trả HTML/login/captcha hoặc file không phải PDF. Ứng dụng sẽ không lưu chúng dưới dạng PDF.

## Kiểm thử và giới hạn

- **60/60 backend tests đạt**, bao gồm các bài thử mới cho tra DOI hàng loạt, tải PDF được tìm từ OpenAlex, Content-Type sai, 403, API lỗi và không có bản OA.
- Đã kiểm tra biên dịch mã Python. **Chưa kiểm thử được Streamlit UI bằng runtime** vì môi trường này không có Streamlit.
- Môi trường lập trình ở đây không kết nối Internet để kiểm tra các nhà cung cấp API hay một DOI thực ngoài đời. Vì vậy không cam kết mọi bài sẽ tải được trong thực tế; người dùng cần chạy lệnh chẩn đoán trên Windows và gửi cột `Status/Error` nếu còn lỗi.
- Không nhúng `.env` chứa khóa API hoặc email thực tế. `.env.example` chỉ gồm placeholder.
