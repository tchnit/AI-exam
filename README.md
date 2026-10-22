# AICB — Phòng luyện thi

Ứng dụng Python cho VPS tự host: Flask + SQLite, HTML/CSS/JavaScript thuần, không cần Node hoặc bước build frontend.

## Chạy trên máy của bạn

Python 3.11+ và hệ điều hành Linux cho Gunicorn. Mở terminal trong thư mục `web/`:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
sh run.sh
```

`run.sh` lắng nghe **0.0.0.0:8766** để máy khác truy cập được. Trên máy đang chạy, mở **http://127.0.0.1:8766**; từ máy khác, mở **http://IP_MAY_CHU:8766** và cho phép cổng TCP 8766 trong firewall/security group nếu cần. `0.0.0.0` là địa chỉ bind, không phải địa chỉ để khách truy cập. Chạy trực tiếp bằng script thì để `TRUST_PROXY` tắt; không bật tin proxy headers khi cổng này nhận request trực tiếp từ Internet.

Có thể dừng bằng Ctrl+C. Database và khóa cookie được tạo trong `instance/` khi khởi động; không xóa thư mục này khi cập nhật. Gunicorn tạo ứng dụng một lần với `--preload`, dùng chung khóa bền vững giữa các worker. Không dùng Flask development server khi public.

## Những gì đã có

- Nhập biệt danh 2–30 ký tự, không đăng nhập.
- Mỗi lượt mới lấy ngẫu nhiên 40 câu khác nhau từ 385 MCQ đã rà soát; 45 phút/lượt. Giữ thứ tự lựa chọn để lời giải không lệch đáp án.
- Câu được chọn lưu lên máy chủ ngay; nháp chưa đồng bộ được giữ ở trình duyệt và tự thử lại khi có mạng. Tải lại trang có thể tiếp tục lượt cũ bằng cookie của cùng trình duyệt. Khi bắt đầu lượt mới, bài cũ chưa nộp được bỏ, không đưa lên BXH.
- Máy chủ giữ đáp án, thời hạn và chấm điểm; một lượt chỉ chốt một kết quả kể cả nộp lặp/đồng thời. Đúng 1, sai/trống 0; thang 10. Hết giờ chỉ chấm câu đã nhận trước hạn.
- Bài hết giờ được chốt khi có request đọc bài/BXH/lịch sử hoặc nộp; không cần cron. Kết quả vẫn dùng deadline thật, không dùng thời điểm request đến muộn.
- Kết quả công khai có câu đã chọn, đáp án, giải thích, nguồn và đúng/tổng theo chủ đề. Đây là đánh giá ôn tập: >=8 nắm khá vững; >=5 cần củng cố; dưới 5 cần ôn lại, không phải điểm chứng nhận.
- BXH xếp theo **lượt thi**: số đúng giảm dần, thời gian tăng dần, rồi thời điểm nộp sớm hơn; phân trang 20 lượt. Lịch sử có tìm biệt danh, bao gồm phiên bản cũ. Tên trùng không được gộp thành một người.
- Mỗi lượt lưu snapshot câu hỏi/đáp án để thay đổi ngân hàng không đổi điểm cũ. BXH chỉ so cùng phiên bản ngân hàng và cấu hình đề 40 câu/45 phút.
- Nội dung, biệt danh và giải thích được render bằng DOM text, không đưa dữ liệu người dùng vào HTML thực thi. API ghi kiểm Origin/cookie và không cho trình duyệt khác sửa bài. Bài chưa nộp và đáp án trước nộp không có API đọc công khai.

## Biệt danh, cookie và IP

Cookie ký, HttpOnly, SameSite=Lax nhận lại **trình duyệt**, không xác minh người thật. Xóa cookie/ẩn danh/đổi thiết bị sẽ tạo ID mới. MAC của máy truy cập không khả dụng qua website Internet. Không khóa người thi theo IP vì cùng Wi-Fi/CGNAT có thể chung IP.

IP được HMAC bằng khóa server để hạn chế spam, không đưa vào API/BXH công khai. Giới hạn mặc định: 10 lượt mới/trình duyệt/giờ và 120 lượt mới/IP/giờ (tính cả bài bỏ). Người dùng có thể đổi IP/cookie để né; không coi đây là chống gian lận nghiêm ngặt. nginx có thể lưu IP thật trong access log tiêu chuẩn: quyền đọc/log retention do quản trị VPS quản lý.

`TRUST_PROXY=1` chỉ bật khi request thực sự đi qua nginx tin cậy. Cấu hình mẫu ghi đè `X-Forwarded-For` bằng IP kết nối, không tin header tự khai. Service production dưới đây dùng nginx và giữ Gunicorn trên localhost; đây là cách chạy riêng với `run.sh` truy cập trực tiếp qua cổng 8766.

## Deploy VPS Linux qua IP

Ví dụ Ubuntu/Debian, giả định có quyền quản trị và cổng 8766 nội bộ chưa bị chiếm. Các lệnh dưới đây chạy **trên VPS**, sau khi đã copy nội dung `web/` vào `/opt/aicb-quiz/`. Chỉ copy ứng dụng; không copy PDF, HTML gốc có đáp án, `.venv/`, dữ liệu thử hoặc `instance/` của máy phát triển.

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv nginx
sudo useradd --system --user-group --home-dir /opt/aicb-quiz --no-create-home aicb
cd /opt/aicb-quiz
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo install -d -o aicb -g aicb -m 700 instance
sudo cp deploy/aicb-quiz.service /etc/systemd/system/aicb-quiz.service
sudo systemctl daemon-reload
sudo systemctl enable --now aicb-quiz
sudo systemctl status aicb-quiz --no-pager
```

Nếu user `aicb` đã tồn tại thì bỏ lệnh `useradd`. Nếu cổng 8766 đã có dịch vụ khác, chọn cổng trống và sửa **cả** service lẫn nginx; không dừng dịch vụ khác một cách tự động.

Sửa `YOUR_VPS_IP` trong `deploy/nginx.conf` thành IP công khai thực tế, sau đó:

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/aicb-quiz
sudo ln -s /etc/nginx/sites-available/aicb-quiz /etc/nginx/sites-enabled/aicb-quiz
sudo nginx -t
sudo systemctl reload nginx
```

Kiểm tra site mặc định/cấu hình nginx đang có để request gửi vào IP đến đúng ứng dụng. Không xóa hoặc ghi đè các site khác. Mở cổng 80 ở firewall/security group nếu cần, giữ nguyên quyền SSH. Sau đó truy cập `http://YOUR_VPS_IP` bằng trình duyệt ngoài VPS.

Mẫu trên chạy HTTP qua IP để khởi động dễ dàng. **Khi public, nên cấu hình HTTPS với chứng chỉ phù hợp IP hoặc domain thực tế**, rồi đặt `COOKIE_SECURE=1` trong `/etc/aicb-quiz.env` và restart service. Không bật `COOKIE_SECURE=1` khi vẫn truy cập HTTP: browser sẽ không gửi cookie, không tiếp tục/nộp bài được. HTTP không bảo vệ cookie và câu trả lời trước người có thể nghe lén mạng. Chưa tự tạo certificate hoặc thay đổi firewall/SSL trên VPS của bạn.

Các biến môi trường tùy chọn:

| Biến | Mục đích |
| --- | --- |
| `QUIZ_DATABASE` | Đường dẫn tuyệt đối tới file SQLite, mặc định `instance/quiz.sqlite3`. Với systemd mẫu, giữ DB trong `instance/` hoặc sửa `ReadWritePaths` tương ứng. |
| `SECRET_KEY` | Khóa ngẫu nhiên bền vững. Bỏ trống thì dùng `instance/secret.key` tạo một lần, mode 600. Không đưa khóa vào repo hoặc lệnh có thể lộ qua history. |
| `TRUST_PROXY` | `1` khi đứng sau đúng một nginx/cloudflared trên cùng máy; chỉ request từ loopback được tin forwarded headers. |

### Link công khai tạm thời bằng Cloudflare Tunnel

Khi chạy `cloudflared` trên cùng máy, khởi động ứng dụng với `TRUST_PROXY=1`, rồi chạy `cloudflared tunnel --url http://127.0.0.1:8766 --no-autoupdate`. Dùng URL HTTPS `trycloudflare.com` được in ra. Ứng dụng chỉ tin forwarded headers từ loopback để HTTPS/Origin hoạt động qua tunnel; request trực tiếp từ mạng vẫn không được tự khai proxy headers.

Giữ cả Gunicorn và cloudflared chạy ngầm bằng nohup nếu thoát SSH. Quick Tunnel là link tạm, đổi khi khởi tạo tunnel mới và không có đảm bảo uptime; dùng tunnel có tên/domain riêng khi cần địa chỉ ổn định. Link công khai cho phép người khác truy cập website và lịch sử/BXH theo thiết kế.
| `COOKIE_SECURE` | `1` chỉ sau khi HTTPS hoạt động. |

## Cập nhật và sao lưu

Giữ nguyên `instance/` và khóa qua mỗi lần cập nhật. Chép code/data mới, cài requirements nếu thay đổi, chạy tests, rồi `sudo systemctl restart aicb-quiz`. Không xóa database hoặc chạy script reset trên dữ liệu thật. Khởi động chỉ tạo bảng/index còn thiếu; không DROP hoặc xóa điểm.

Backup SQLite khi app đang chạy bằng SQLite backup API, không chỉ copy file `.sqlite3` trong lúc WAL đang có dữ liệu:

```bash
sudo -u aicb /opt/aicb-quiz/.venv/bin/python - <<'PY'
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
root = Path('/opt/aicb-quiz/instance')
target = root / ('backup-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '.sqlite3')
with sqlite3.connect(root / 'quiz.sqlite3') as source, sqlite3.connect(target) as dest:
    source.backup(dest)
target.chmod(0o600)
print(target)
PY
```

Sao lưu thêm `instance/secret.key` (hoặc `SECRET_KEY` nếu dùng biến môi trường) tới nơi riêng có kiểm soát truy cập. Không phục vụ backup/DB/khóa qua nginx. Thử restore trên bản sao trước. Khi restore thật: dừng service, giữ lại bản hiện tại để rollback, khôi phục backup vào đúng đường dẫn và quyền user `aicb`, bỏ các file WAL/SHM cũ **chỉ khi service đã dừng và đã giữ bản hiện tại**, rồi khởi động lại. Không thay khóa nếu muốn cookie hiện tại còn hiệu lực.

Xem log: `sudo journalctl -u aicb-quiz -n 100 --no-pager`.

## Kiểm thử

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests dùng DB tạm, không chạm dữ liệu thật: đề ngẫu nhiên/không trùng, không lộ đáp án, chấm đúng/sai/trống, tiếp tục bài, hết giờ, nộp lặp/đồng thời, quyền sửa bài, dữ liệu giả, giới hạn IP, thứ tự BXH, trùng tên, lịch sử sau restart/đổi ngân hàng và security headers.

## Nội dung và giới hạn

Xem [QUESTION_REVIEW.md](QUESTION_REVIEW.md) cho 4 câu tạm loại và 7 câu sửa lời giải/phương án. Các PDF đối chiếu là nguồn theo chủ đề; chưa dựng số trang giả cho từng câu. Không đưa 131 tự luận vào tự chấm; không chép thêm raw dataset/ảnh/PDF lên public host. Ngân hàng được lưu phía server ở `data/questions.json`, không thuộc `static/`.

SQLite phù hợp ứng dụng nhỏ trên một VPS với transaction ngắn; nhiều ghi đồng thời có thể chờ. Chưa đo tải lớn, chưa kiểm trên VPS thực tế và chưa có tài khoản/giám sát chống gian lận. Lịch sử công khai chi tiết đáp án sau nộp nên người thi có thể ôn/tra cứu đáp án; điểm là điểm luyện tập.
# AI-exam
