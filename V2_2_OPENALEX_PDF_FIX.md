# V2.2 — Fix OpenAlex PDF links (17/10/2026)

## Nguyên nhân cảnh báo “Một số bài không có PDF Open Access trực tiếp”

Trong V2.1, `clients/openalex.py` đọc link PDF OpenAlex ở `best_oa_location.pdf.url` hoặc `locations[].pdf.url`. Tuy nhiên API OpenAlex hiện tại trả `best_oa_location.pdf_url`, `primary_location.pdf_url` và `locations[].pdf_url` là **chuỗi URL trực tiếp**. Vì vậy ứng dụng bỏ sót nhiều link OA trong kết quả API dù bài có bản PDF công khai.

Tài liệu OpenAlex: https://help.openalex.org/data/locations/ ; https://help.openalex.org/api/authentication/

Lưu ý: một số bài **thực sự không có PDF Open Access trực tiếp**, hoặc máy chủ PDF từ chối tải. Bản sửa chỉ tìm và tải các liên kết công khai hợp pháp, không vượt paywall hay CAPTCHA.

## Thay đổi V2.2

1. Đọc đúng `location.pdf_url` theo API OpenAlex hiện hành ở cả `best_oa_location`, `primary_location` và `locations`.
2. Tương thích ngược với `pdf.url` trong dữ liệu cache hoặc test cũ.
3. Chỉ nhận PDF của `primary_location`/`locations` khi chúng có `is_oa=true`; không dùng nguồn không OA. `best_oa_location` được mặc định là OA nếu không nêu trạng thái trái ngược.
4. Khi bài đã lưu một link PDF (nhưng link lỗi hoặc hết hạn), **vẫn tra cứu lại DOI bằng OpenAlex** để thử các nguồn OA thay thế, không dừng ở link cũ.
5. Nếu Unpaywall trả lỗi, hiển thị dấu hiệu thất bại khi không tìm được PDF, thay vì âm thầm báo không có OA.
6. Cảnh báo Streamlit nêu rõ xem cột `Error` và phân biệt không có OA, lỗi HTTP 403, hoặc lỗi nguồn metadata.
7. Thêm 4 test hồi quy bằng cấu trúc OpenAlex thật hiện hành, bao gồm fallback `403 → OA repository PDF`.

## Kết quả kiểm thử trong môi trường phát triển

- **64/64 backend tests thành công**, chạy bằng `python -m pytest -q --ignore=tests/test_app_ui.py`.
- Python source đã được kiểm tra biên dịch (`compileall`).
- Không chạy được Streamlit UI test vì môi trường này không có thư viện Streamlit.
- Chưa xác nhận download từ API/website thật trong môi trường này vì không có quyền truy cập mạng trực tiếp của ứng dụng. Mock test xác minh logic, không cam kết mọi DOI tải được.

## Nâng cấp Windows

1. Dừng Streamlit cũ (`Ctrl+C`).
2. Giải nén ZIP vào **thư mục V2.2 mới**, không trộn vào V2.1. File `data/research.db` và 5 PDF mẫu từ bản trước nằm trong ZIP.
3. Mở PowerShell tại thư mục vừa giải nén.
4. Cài và cấu hình (email thật của bạn, không chia sẻ `.env`):

```powershell
uv sync --extra dev
Copy-Item .env.example .env
notepad .env
```

Cấu hình khuyến nghị trong `.env`:

```ini
LAW_RESEARCH_UNPAYWALL_EMAIL=your-real-email@example.com
LAW_RESEARCH_OPENALEX_API_KEY=your-own-key-if-available
LAW_RESEARCH_OPENALEX_EMAIL=your-real-email@example.com
```

`LAW_RESEARCH_OPENALEX_API_KEY` là key API riêng lấy từ OpenAlex. Nhiều truy vấn demo vẫn có thể chạy không có key, nhưng cần key miễn phí cho sử dụng thường xuyên. **Không gửi API key trong hội thoại hoặc ZIP.**

5. Khởi động mới sau khi lưu `.env`:

```powershell
uv run streamlit run app/main.py
```

6. Trong **Paper Library**, chọn vài bài và `Download selected PDFs`; hoặc trong **Download Manager** chọn `Retry failed` với tác vụ đã tạo ở phiên vừa chạy. Xem `Status` và `Error` của từng bài. Nút **Tải các PDF về máy của tôi (ZIP)** chỉ xuất hiện nếu có PDF thật đã tải thành công.

7. Chẩn đoán DOI cụ thể:

```powershell
uv run python scripts/diagnose_pdf.py 10.1371/journal.pone.0266781
```

Nếu lỗi vẫn tiếp diễn, gửi lại **DOI** và 2 cột **Status / Error** (không gửi `.env`).

## Các trường hợp V2.2 không thể tự sửa

- Nguồn chỉ công bố landing page, không có bản Open Access có thể tải.
- Website đòi đăng nhập, mua bài, xác minh CAPTCHA hoặc gửi HTTP 403.
- OpenAlex/Unpaywall không biết đến bản OA dù tác giả có chia sẻ hợp pháp ở nguồn khác.
- Máy người dùng bị chặn mạng, DNS, proxy, hoặc không có quyền ghi `data/downloads`.
