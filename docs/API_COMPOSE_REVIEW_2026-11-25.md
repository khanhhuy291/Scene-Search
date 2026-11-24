# Rà soát API và thống nhất Docker Compose — 2026-11-25

## Kết quả triển khai

Repo chỉ còn `docker-compose.yml`: build source tại local hoặc GCP GPU VM.
8 service: frontend, api, worker, embedding-api, postgres, redis, minio, qdrant.
Cấu hình dựa trên stack local đầy đủ, giữ project `scenesearch-local`, tên service,
collection `scenes_local` và các volume để tiếp tục dùng dữ liệu hiện có.
Đã bỏ `docker-compose.local.yml` và `docker-compose.deploy.yml` theo yêu cầu hợp nhất.

`Makefile` dùng một biến `COMPOSE`. Các target deploy không còn gọi script không
tồn tại; bỏ target `deploy-only` bị định nghĩa hai lần. `deploy`/`deploy-gcp` build
trên máy đang chạy lệnh; `deploy-only` dùng image đã có; `docker-infra` chạy hạ tầng.
Đã bỏ các alias mang tên Cloud Run để tránh nhầm nền tảng triển khai.

API/worker dùng cùng cấu hình Postgres, Redis, MinIO, Qdrant và embedding nội bộ.
Frontend build production qua `Dockerfile.prod`, không mount source hay chạy Vite.
Frontend đợi API healthy; worker đợi migration/API healthy. Embedding được gọi qua
`http://embedding-api:8001`, không dùng tên `qwen-embedding` riêng cho deploy.

## Luồng API hiện tại

Điểm vào duy nhất: `app/api/main.py`, router tổng `app/api/v1/__init__.py`, prefix
`/api/v1`. Browser → frontend Nginx → `/api/*` → `api:8000`.
Các client frontend dùng chung `frontend/src/api/base.js`, mặc định `/api/v1`.
Search trước đây hardcode prefix, giờ dùng cùng nguồn cấu hình với auth/admin/etc.

| Nhóm | Luồng chính | Quyền truy cập hiện tại |
| --- | --- | --- |
| `/auth/*` | `api/v1/auth.py` → `services/auth.py` → `repositories/user.py` → PostgreSQL; JWT và blacklist Redis | Login/register public; profile/password cần user; quản trị user cần admin |
| `/search` | `api/v1/search.py` → `search/engine.py` → catalog/Qdrant + encoder remote; trả kết quả theo video và cursor | Public |
| `/ingest/upload` | `api/v1/ingestion.py` → giới hạn 500 MiB/đuôi file → SHA256 → corpus → raw MinIO → claim processing → task status → Celery queue `ingestion` | Admin |
| `/tasks`, `/tasks/{id}` | `repositories/task_status.py`; fallback Celery khi cần | Admin |
| `/videos/{id}`, reprocess | Corpus + index/storage cleanup hoặc enqueue lại | Admin |
| `/media/thumbnail/*`, `/media/clip/*`, `/media/video/*` | `api/v1/media.py` → catalog/corpus → derived MinIO; playback hỗ trợ byte range | Optional auth; nội dung anonymized |
| `/datasets/export` | `services/datasets.py` → ZIP thumbnail anonymized + manifest; xóa ZIP tạm sau trả response | Engineer/admin |
| `/admin/*` | Telemetry, eval, trace, load/unload embedding, enqueue caption refresh | Admin |
| `/chat` | `services/chat_agent.py` → tìm scene + LLM/VLM theo cấu hình | Public |
| `/feedback/rerank` | `services/rlhf.py` → PostgreSQL | Submit optional auth; list/stats/export admin |

Worker: `app/worker/tasks/ingestion.py` → `app/pipelines/ingestion/orchestrator.py`
→ acquire/validate video → trích xuất/xử lý/anonymize → embedding → persist
PostgreSQL/Qdrant/derived MinIO → cập nhật task và trạng thái video.
API upload trả HTTP 202 khi enqueue thành công, không có nghĩa video đã index xong.

## Lỗi đã sửa

1. **Hai luồng upload tự fallback:** frontend thử presigned PUT rồi process; lỗi
   ở process cũng có thể kích hoạt multipart lần nữa. Nay browser chỉ gửi
   multipart qua API cùng origin, có progress và giữ nguyên lỗi enqueue.
   Không cần browser truy cập hostname `minio` trong Docker hay cấu hình CORS S3.
   Nginx cho phép request 512 MiB, API giới hạn file 500 MiB.
2. **Auth tự dựng user khi DB lỗi:** cả `api/deps.py` và `services/auth.py` có
   fallback demo. Đã bỏ. DB lookup lỗi trả 503; token của user không tồn tại trả
   401. Role, active và token_version lấy từ user thật trong DB.
3. **Sai khác môi trường Compose:** thống nhất cùng hạ tầng, tên embedding,
   search Qwen/agentic/rerank, dependency startup, frontend reverse proxy.
4. **Tài liệu/lệnh không còn đúng:** cập nhật README, hướng dẫn GCP, start/stop,
   bulk ingestion, script CUDA recovery và env example. Giữ tài liệu audit/worklog
   lịch sử nguyên nghĩa, nên chúng vẫn có thể nhắc tên file đã bỏ.

## Điểm cần phân biệt khi vận hành

- `/health` của API và embedding là liveness; startup API vẫn log warning và chạy
  khi một số kiểm tra hạ tầng lỗi. Không dùng HTTP 200 này để kết luận search,
  model hoặc ingestion thành công. Model cần được load bởi admin.
- Search public, chat public, media optional auth, feedback submit optional auth
  là chính sách hiện tại của code. Việc hợp nhất Compose không đổi chính sách này.
- `/ingest/presigned-url` và `/ingest/process` vẫn tồn tại cho client cũ; giao diện
  mới không gọi chúng. Nhánh process hiện dùng raw_key làm checksum và không lấy
  video_id client làm ID DB; không có cùng dedup theo SHA256 như multipart.
  Không coi hai contract upload là tương đương. Chưa xóa endpoint tương thích này.
- `SEARCH_RERANK_ENABLED=true` là cấu hình, không bảo đảm reranker đã load/chạy
  thành công. Chưa thực hiện inference model thật trong lần rà soát này.
- GCP dùng Compute Engine GPU VM, build source trực tiếp. Máy mới có volume mới;
  dữ liệu local không tự chuyển lên cloud. Giữ volume hiện có, không chạy down -v.
- Đổi HTTP_BIND_ADDRESS/HTTP_PORT trong env để mở frontend trên VM. Hạ tầng còn
  lại giữ loopback/private. Xem `DOCKER_GCLOUD_GUIDE.md`.

## Kiểm chứng

- `docker compose --env-file app/.env config --quiet`: pass.
- `make -n deploy-gcp local-up deploy-only docker-infra`: đúng cùng file Compose.
- Backend: `/tmp/scenesearch-v3-venv/bin/python -m pytest app/tests -q` với
  `PYTHONPATH=app OPENBLAS_NUM_THREADS=1`, chạy ngoài sandbox vì test có truy cập
  loopback: **490 passed, 2 skipped, 2 warnings** (ML extra chưa cài; warning
  AsyncMock ở test RLHF hiện có).
- Frontend: 13 tests pass, ESLint pass, production build pass. Test mới xác nhận
  upload chỉ gửi một request và giữ lỗi enqueue, không retry bằng transport khác.
- Test auth mới xác nhận user demo không tồn tại bị từ chối và DB lỗi trả 503,
  kể cả đăng nhập bằng credential demo cũ.
- Chưa build lại Docker image, recreate container hoặc chạy upload/inference thật.
  Container đang chạy vẫn dùng image trước thay đổi; áp dụng bằng `make docker-up`.

## Bổ sung: thống nhất env

Đã thay template cũ bằng `app/.env.example` chung và bỏ `.env.local.example`.
`app/.env` được bổ sung các default tương ứng; giữ nguyên toàn bộ 14 assignment
có trước (bao gồm secret, model/LLM và checkpoint privacy), không ghi giá trị vào
báo cáo. Không ghi đè collection hiện dùng, không chuyển dữ liệu.
Compose chỉ giữ override cho network Docker và batch GPU được ghi rõ; các biến
app/search/model khác không còn bị hardcode đè dotenv. Đường dẫn dotenv trong mọi
nhóm Pydantic được cố định theo source. Template bỏ các biến cũ không được tiêu thụ
và dùng `LLM_TIMEOUT` đúng schema. Bootstrap admin hoạt động bằng lệnh tường minh
trong production và đọc cùng dotenv khi chạy native.

Có `make config-check`: kiểm tra Compose + tên biến/biến trùng + typed settings,
không in secret và không kết nối dịch vụ. Unit tests được tách khỏi `.env` của máy
chạy để secret/tuning cá nhân không làm thay đổi kết quả test. Test Compose render
kiểm chứng `.env` đổi rerank/agentic/debug/collection/timeout/dtype và batch GPU
thực sự có hiệu lực; test native kiểm chứng root/app/thư mục khác đọc cùng dotenv.
Hướng dẫn chi tiết và các override có chủ đích nằm trong `DOCKER_GCLOUD_GUIDE.md`.

Kiểm chứng sau chuẩn hóa env: **496 passed, 2 skipped, 2 warnings**; Ruff check và
format pass; `make config-check PYTHON=/tmp/scenesearch-v3-venv/bin/python` pass.
Hai skip là ML extra chưa cài; warning AsyncMock RLHF có từ trước. `.env` vẫn có
quyền 600 và không được Git track. Chưa recreate container hoặc chạy inference thật.
