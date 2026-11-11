# Upload hàng loạt video qua ingestion API

Script `app/scripts/bulk_ingest.py` chạy trên host bằng Python 3.11+, chỉ dùng
standard library; không cần cài dependency backend hay mount video vào worker.
Video được stream multipart vào API, đăng ký vào DB/raw storage rồi xử lý qua
Celery và pipeline hiện tại. Không tự ghi vector hay copy thẳng vào MinIO.

## Chạy

Từ thư mục project, kiểm tra danh sách mà không tạo job:

```bash
python3 app/scripts/bulk_ingest.py --dry-run
```

Thử 10 video đầu trước:

```bash
python3 app/scripts/bulk_ingest.py --limit 10
```

Upload và xử lý toàn bộ thư mục đã chỉ định:

```bash
python3 app/scripts/bulk_ingest.py
```

Mặc định:

- Nguồn: `bdd100k_videos_train_00/bdd100k/videos/train` dưới root project.
- API: `http://localhost:8000/api/v1`.
- Admin: `LOCAL_ADMIN_EMAIL` và `LOCAL_ADMIN_PASSWORD` từ environment hoặc
  `app/.env`. Không ghi credential/token vào manifest.
- Chờ từng job completed/failed trước khi gửi video tiếp theo; không đẩy toàn bộ
  1.000 job vào queue. Model phải ready/busy trước khi chạy.
- API hiện gán `dataset="uploads"` cho video upload, dù nguồn là BDD100K;
  khi test search không lọc theo tên dataset BDD100K chưa được khai báo.
- Manifest: `data/ingestion/bdd100k_train_00.json`; chứa đường dẫn tương đối,
  size/mtime, task_id, video_id, trạng thái, kết quả và lỗi mỗi video.
- Poll 5 giây/lần; timeout request 300 giây; chờ mỗi task tối đa 3.600 giây.
- Dừng sau 5 job thất bại liên tiếp để tránh ingest cả corpus khi pipeline lỗi.

Sau khi 10 video xong, chạy lệnh không có `--limit`: script bỏ qua 10 video đã
completed và xử lý phần còn lại. Một số tham số khác:

```bash
python3 app/scripts/bulk_ingest.py --retry-failed
python3 app/scripts/bulk_ingest.py --source /path/to/videos --state /path/to/manifest.json
python3 app/scripts/bulk_ingest.py --recursive --poll-interval 3 --task-timeout 7200
```

## Tiếp tục và xử lý lỗi

Ctrl+C dừng uploader; job đã gửi vẫn có thể tiếp tục chạy trong worker. Chạy lại
cùng lệnh và cùng manifest để theo dõi task đang xử lý, thay vì gửi một job trùng.
File completed trong manifest được bỏ qua; file failed/cancelled chỉ được submit
lại khi có `--retry-failed`. Không sửa/di chuyển video trong lúc upload.

Nếu mất kết nối sau khi gửi upload nhưng chưa nhận task_id, script ghi
`upload_unknown` và dừng. Kiểm tra `/api/v1/tasks` hoặc trang ingestion để tìm
job tương ứng trước khi điều chỉnh bản ghi manifest; không tự retry upload có
kết quả chưa rõ vì API hiện chưa có idempotency key cho request.

Manifest gắn với source và địa chỉ API, chưa gắn với ID của database. Nếu xóa
volume DB/Qdrant hoặc chuyển sang một instance khác ở cùng URL, dùng manifest
mới để không bỏ qua dữ liệu chỉ vì lần ingest cũ đã completed.

Xem tiến độ trong giao diện ingestion, hoặc:

```bash
docker compose --env-file app/.env -f docker-compose.local.yml logs -f --tail=100 worker
```

Sau khi có job completed, thử search trong giao diện. Catalog payload được cache
tối đa 15 phút. Nếu đã search trong lúc batch còn chạy và muốn thấy video mới
ngay, có thể khởi động lại riêng API sau khi batch hoàn tất:

```bash
docker compose --env-file app/.env -f docker-compose.local.yml restart api
```

## Phạm vi kiểm chứng và giới hạn hiện tại

Đã dry-run trên thư mục thực: 1.000 file MOV, khoảng 18.44 GiB; chưa thực hiện
upload hàng loạt. Bốn test qua: resume task, bỏ qua file đã hoàn thành, không tự
submit lại khi mất response upload và kiểm tra multipart stream đọc được bởi
parser dùng trong FastAPI/Starlette. Các test không gửi video vào server thật.

Script sử dụng pipeline hiện có. Luồng playback và layout derived đã được sửa
theo [VIDEO_PLAYBACK.md](VIDEO_PLAYBACK.md): một video đầy đủ dùng chung, thumbnail
riêng từng segment và player giới hạn theo timestamp. Các hạn chế privacy của
thumbnail và metadata fallback vẫn cần xem xét riêng.
Nếu chưa cấu hình LLM, caption/concept được tạo theo fallback nên không nên coi
kết quả lọc metadata là nhãn ground truth. Nên xem kết quả 10 video đầu rồi mới
chạy toàn bộ corpus.
