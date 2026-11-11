# Chạy SceneSearch bằng Docker trên máy local

Các bước vận hành chi tiết từ khởi động đến tắt stack nằm trong
[LOCAL_START_STOP.md](LOCAL_START_STOP.md).

Stack riêng: `docker-compose.local.yml`, project `scenesearch-local`. Không dùng
Google Cloud hay các endpoint DB/storage cũ. Dữ liệu nằm trong các named volume
của project này. Cần Docker Compose và NVIDIA Container Toolkit cho GPU embedding.

MinIO được build từ source revision `7aac2a2c5b7c` bằng
`deploy/local-minio/Dockerfile`, vì image community cũ không còn pull được.
Tham khảo [thông báo upstream](https://github.com/minio/minio#readme).
Lần build đầu cần tải Go modules, PyTorch/CUDA và model weights nên lâu hơn
những lần khởi động lại dùng cache.

## Cấu hình và khởi động

Lần cài đặt này đã tạo `app/.env` với credential ngẫu nhiên (quyền 600).
Nếu cài máy mới, copy `app/.env.local.example` sang `app/.env`, thay tất cả giá trị
`change-me` bằng secret riêng. Không ghi đè `.env` đang dùng nếu chưa sao lưu.

```bash
make local-up
make local-admin
make local-ps
```

`local-up` build và chạy frontend, API, worker, embedding, PostgreSQL, Redis,
MinIO và Qdrant. API chạy Alembic trước Uvicorn; worker đợi API healthy.
Model tự tải vào volume Hugging Face trong lần đầu. `/health` của embedding là
liveness, cần `/model/status` để biết model đã load xong hay chưa.

| Chức năng | Địa chỉ |
|---|---|
| Web | http://localhost:5173 |
| Swagger | http://localhost:8000/docs |
| API liveness | http://localhost:8000/health |
| MinIO console | http://localhost:9001 |
| Qdrant dashboard | http://localhost:6333/dashboard |

Các cổng chỉ bind loopback. PostgreSQL và Redis chỉ truy cập qua network Docker.
Credential admin nằm trong `app/.env`: `LOCAL_ADMIN_EMAIL`, `LOCAL_ADMIN_PASSWORD`.
MinIO dùng `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` trong cùng file.
`make local-admin` tạo tài khoản DB thật, chạy lại không đổi mật khẩu user đã có.

Giao diện đăng nhập dùng tài khoản thật trong DB. Các tài khoản demo cũ không
được tạo trong stack này; frontend không tự đăng nhập hay điền mật khẩu demo.
Nếu nhận 401, kiểm tra đúng email/mật khẩu local ở trên hoặc dùng tài khoản đã
đăng ký. Sau khi cập nhật frontend, tải lại trang bằng Ctrl+Shift+R.

## Vận hành

```bash
make local-logs
make local-down
make local-up
```

`local-down` giữ nguyên dữ liệu/model cache. Chưa có lệnh tự xóa volume.
Nếu chỉ đổi code mà không muốn khởi động ngay: `make local-build`.

### Làm mới caption fallback

Caption dạng mẫu `Dashcam driving scene at ...` có thể được tạo lại từ thumbnail
đã lưu trong MinIO mà không chạy lại embedding hay tạo playback. Đăng nhập lấy
Bearer token như frontend, rồi gọi endpoint admin:

```bash
# Chỉ làm mới các cảnh của một video
curl -X POST http://localhost:8000/api/v1/admin/captions/refresh \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"video_ids":["VIDEO_UUID"]}'

# Bỏ video_ids hoặc gửi mảng rỗng để làm mới mọi caption fallback
curl -X POST http://localhost:8000/api/v1/admin/captions/refresh \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{}'
```

Endpoint trả `task_id` (HTTP 202). Theo dõi bằng
`GET /api/v1/tasks/{task_id}`. Job chỉ cập nhật caption, metadata, retrieval tags
và present/absent concepts trong Qdrant; thumbnail lấy từ bucket derived. Sau khi
cập nhật, catalog search được báo làm mới và nạp lại ở request search kế tiếp.

Các target `docker-up`/`deploy` cũ vẫn trỏ cấu hình cũ; dùng các target `local-*`
cho stack này. Các cấu hình triển khai cũ vẫn được giữ để chờ duyệt riêng.

## Giới hạn

Local search mặc định dùng Qwen, tắt agentic/reranking. Qdrant mới dùng named
vectors `qwen` 2048 chiều và `siglip` 768 chiều phù hợp ingestion hiện tại.
Chat/VLM metadata cần cấu hình `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` nếu muốn
dùng; file mẫu để trống API key. Ứng dụng local chưa đồng nghĩa offline hoàn toàn.

Các lỗi ingestion/media/privacy đã ghi trong `LOCAL_REVIEW_2026-11-11.md` chưa
được mặc định sửa hết khi dựng Docker. Chạy stack thành công không chứng minh
chất lượng tìm kiếm hay pipeline với video thật. Kết quả smoke test của lần triển
khai này sẽ được ghi bên dưới sau khi hoàn tất.

## Kiểm chứng triển khai ngày 2026-11-11

- Đã build API, frontend, embedding GPU và MinIO từ source.
- Đã áp toàn bộ Alembic migrations vào PostgreSQL local mới và tạo admin thật;
  bootstrap chạy lại không đổi credential.
- 18 test Qdrant bootstrap/write path qua; Ruff check/format các file Python
  thay đổi đều qua.
- HTTP thực tế: web, API, login/profile admin, proxy qua frontend, task list rỗng,
  MinIO và Qdrant đều qua. Truy cập task list không token trả 401.
- Worker Celery trả `pong` qua Redis.
- Collection Qdrant tạm: khởi tạo schema mới, ghi cả hai tower qua application
  write path, query Qwen và dọn collection test đều qua; corpus chính vẫn rỗng.
- CUDA thực thi được trong embedding container: PyTorch `2.15.0+cu132`, CUDA
  `13.2`, GPU `NVIDIA GeForce RTX 5060 Laptop GPU`.

- Cả 8 container đã chạy; model chuyển `ready`, Qwen và SigLIP dùng khoảng
  4445.5 MiB (4.34 GiB) GPU memory allocated khi vừa load.
- 16 HTTP smoke checks qua: gồm Qwen text/image embedding (2048 chiều), SigLIP
  text/image embedding (768 chiều), vector hữu hạn và chuẩn L2 gần 1, cùng search
  corpus rỗng trả HTTP 200 và results rỗng. Ảnh kiểm tra là ảnh màu tổng hợp 224×224.

Bằng chứng API/hạ tầng: `local-core-smoke-results.json`; bằng chứng model/search:
`local-smoke-results.json` (12:31 ngày 2026-11-11, giờ Việt Nam).
Chưa upload video thật; chưa kiểm thử ingestion end-to-end hay độ chính xác retrieval.

Upload hàng loạt video từ host qua đúng API/pipeline: xem [BULK_INGEST.md](BULK_INGEST.md)
và script `app/scripts/bulk_ingest.py` (có dry-run, giới hạn số video và resume).

Luồng video đầy đủ, giới hạn phát theo segment và layout derived hiện tại:
[VIDEO_PLAYBACK.md](VIDEO_PLAYBACK.md). Mười video thử cũ đã được dọn để ingest lại.

## Khôi phục lỗi CUDA sau khi máy ngủ hoặc GPU fault

Nếu inference báo `unspecified launch failure`, `illegal memory access` hoặc
driver ghi Xid/MMU fault, không tiếp tục upload vào cùng context CUDA. Khởi động
lại riêng service GPU rồi đợi model ready:

```bash
docker compose --env-file app/.env -f docker-compose.local.yml restart embedding-api
```

Lệnh này giữ nguyên video, DB và cache weights. Sau khi model ready, tiếp tục các
job failed bằng `python3 app/scripts/bulk_ingest.py --limit 10 --retry-failed`.
Uploader bỏ qua video completed và kiểm tra model trước mỗi upload mới.

Nếu restart container vẫn báo `CUDA initialization: CUDA unknown error`, cần
khôi phục UVM trên host bằng quyền sudo. Chạy trực tiếp trong terminal:

```bash
bash app/scripts/recover_local_cuda.sh
```

Script xin sudo trước khi dừng embedding, reload riêng `nvidia_uvm` (không force),
tạo lại container để nhận device node mới, kiểm tra CUDA kernel và chờ model
ready có GPU allocations. Không thay cấu hình driver hoặc reboot máy. Nếu UVM
đang được ứng dụng CUDA khác sử dụng, lệnh unload dừng với lỗi để tránh ép gỡ.
Tham khảo [báo cáo suspend/UVM trên NVIDIA Developer Forums](https://forums.developer.nvidia.com/t/bug-nvidia-uvm-needs-to-be-removed-and-re-inserted-in-order-to-work-after-wakeup-from-suspend/188453).

Với `ML_DEVICE=cuda`, embedding service hiện từ chối fallback CPU: CUDA không khởi
tạo được sẽ báo error thay vì ready. Để chạy CPU có chủ đích, cần cấu hình device
riêng; không diễn giải request HTTP 200 là bằng chứng đang dùng GPU.

Embedding service chuyển sang error/health 503 khi phát hiện lỗi CUDA sticky;
không trả ready lại ở cuối request lỗi. Load model trong cùng context hỏng sẽ
bị từ chối; cần restart process/container. Docker không tự restart container chỉ
vì health chuyển unhealthy. Trong lúc chạy batch, giữ máy không suspend.

Chẩn đoán ngày 2026-11-11: kernel ghi suspend/resume lúc 14:46 và Xid 31 lúc
15:19 trong process embedding. Suspend là một khả năng liên quan, chưa chứng
minh nguyên nhân gốc. NVIDIA mô tả Xid 31 là GPU memory page fault và khuyến nghị
restart ứng dụng rồi điều tra nếu tái diễn:
[Xid catalog](https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html).
