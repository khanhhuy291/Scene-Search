# Rà soát chuyển SceneSearch sang local — 2026-11-11

> Báo cáo này ghi nhận trạng thái trước đợt build Docker local. Công việc tiếp
> theo đã thêm stack local riêng, bootstrap admin và sửa khởi tạo named vectors
> trên Qdrant mới; xem `LOCAL_DOCKER.md` và các smoke-test artifact để biết trạng
> thái sau triển khai. Danh sách xóa file bên dưới vẫn chưa được thực hiện.

## Phạm vi và kết quả kiểm tra

Đã đọc router API, auth dependencies, dịch vụ auth/dataset/chat, ingestion worker,
pipeline preview/indexing, cấu hình hạ tầng, frontend upload, Compose, Makefile và CI.
Đây là báo cáo rà soát; chưa sửa code/config cũ, chưa xóa file, chưa khởi động stack,
chưa upload video và chưa gọi các dịch vụ cloud. Worktree đã có sẵn file `=` bị xóa;
giữ nguyên thay đổi đó.

Môi trường kiểm thử riêng: `/tmp/scenesearch-review-venv`, Python 3.12.14,
dependency từ `app/requirements.lock`, không cài ML extra/model weights.

- Pytest: **469 passed, 1 failed, 2 skipped, 2 warnings**, tổng 472 test.
- Test lỗi: `tests/unit/test_embedding_api.py::test_load_and_unload_model_lifecycle`.
  Test mock Qwen nhưng `_load_model()` còn gọi SigLIP thật; thiếu `open_clip`.
  Cần mock cả SigLIP để test lifecycle độc lập, rồi kiểm thử model thật riêng.
- Hai test skip trong `test_config_ml.py` cần ML extra.
- Hai warning trong test RLHF: mock `session.add` trả coroutine không được await;
  cần dùng mock đồng bộ cho phương thức này, không đổi SQLAlchemy `add` thành await.
- Ruff check: qua với các thư mục backend hiện có; chưa chạy format check.
- `alembic heads`: một head `20260831_0008`; chưa áp migration vào DB thật.
- Compose parse qua bằng `--no-env-resolution`; không chứng minh các dịch vụ chạy.
- Không có Node/npm trên PATH, không có frontend/node_modules: chưa chạy frontend
  test/lint/build.
- Chạy pytest trong sandbox bị treo ở dependency đồng bộ; chạy lại ngoài sandbox
  đã hoàn tất. Không kết luận đây là lỗi ứng dụng.

Log kiểm tra ở `/tmp/scenesearch-review-pytest.log` và
`/tmp/scenesearch-review-ruff.log` (file tạm, không phải artifact lưu bền).

## Các phát hiện ưu tiên

### 1. Local Compose thiếu backing services

`docker-compose.yml` chỉ có API, worker, embedding-api và frontend.
`app/.env.example` lại trỏ `postgres`, `redis`, `minio`, `qdrant` qua Docker DNS.
Một máy local mới không có các service này sẽ không chạy được các nghiệp vụ.
Chưa có `app/.env` trong checkout hiện tại.

Cần thêm PostgreSQL/Redis/MinIO/Qdrant local, volume dữ liệu và healthcheck;
API phải đợi DB trước bước Alembic, worker nên đợi API hoàn tất migration.
Tách rõ cấu hình host (`localhost`) và trong container (tên service).

### 2. Collection mới và vector ghi/đọc không thống nhất

`app/infrastructure/qdrant.py:193` tạo collection với một vector không tên.
`.env.example` đặt `QDRANT_WRITE_VECTOR_NAME=qwen`; write path trong
`app/search/index.py` bọc vector thành named vector, và search mode qwen trong
`app/search/engine.py:464` yêu cầu tên `qwen`.

Do đó cold start trên Qdrant trống có contract không khớp. Cần thống nhất schema
collection named `qwen` (2048), và xem xét thêm `siglip` (768) nếu dùng hybrid;
kiểm thử create → write → search trên collection mới, không chỉ mock remote index.

### 3. Auth dự phòng vượt qua nguồn dữ liệu người dùng

`app/services/auth.py:39` cho phép credential demo cố định khi truy vấn DB lỗi.
`app/api/deps.py` dựng user từ JWT claims khi DB lỗi, và có ngoại lệ cho hai UUID
demo khi không tìm thấy user. Các nhánh này không giới hạn development.

Khi DB mất kết nối, trạng thái active/role/token_version không còn được kiểm tra
theo DB. Cần trả lỗi dịch vụ khi DB lỗi, từ chối user không tồn tại, và tạo admin
local qua công cụ bootstrap rõ ràng thay vì tài khoản dự phòng ngầm.

### 4. Media public và có thể trả video raw

Router `app/api/v1/media.py:32` dùng `get_current_user_optional`, nên không bắt buộc
đăng nhập. `_resolve_media_location_fast()` ưu tiên raw bucket, `_read_object()`
cũng tìm raw bucket. Không presign raw trong wrapper MinIO không ngăn được việc
proxy đọc raw rồi stream cho client.

Đây là hành vi thực của code; README mô tả media bắt buộc đăng nhập và chỉ trả
derived không còn đúng. Test media hiện cũng chấp nhận optional authentication.
Cần quyết định lại quyền xem media và chỉ tìm derivative ở luồng hiển thị/export.

### 5. Preview các scene ghi đè nhau, lỗi encode bị bỏ qua

`app/pipelines/ingestion/preview_generator.py:82` dùng chung `<video_id>.mp4`
cho mọi scene. Scene sau ghi đè scene trước trong storage; các point cùng trỏ tới
preview cuối. Preview là clip ngắn bắt đầu từ đầu scene, trong khi frontend còn
seek theo timestamp toàn video: cần thống nhất offset khi phát clip.

Dòng 98–102 bắt mọi lỗi encode và có thể tạo file rỗng rồi tiếp tục upload.
Không được báo ingestion thành công với preview rỗng/hỏng. Nên dùng key riêng
theo scene và fail/retry khi encode lỗi.

### 6. DELETE video bỏ sót object thực tế

`app/api/v1/ingestion.py:381` xóa prefix `raw/<id>/`, `videos/<id>/`,
`thumbnails/<id>/`. Nhưng upload lưu raw `<id>.<suffix>`, preview lưu `<id>.mp4`,
thumbnail lưu `<id>/frame_*.jpg`.

Response 204 không có nghĩa object đã được xóa. Cần deletion plan chứa
raw_object_key và các derivative key thật, đồng thời vô hiệu cache media/catalog.
Test hiện chỉ assert các prefix cũ nên chưa bắt lỗi contract này.

### 7. Direct upload chưa được xác nhận trước enqueue

`app/api/v1/ingestion.py:112` chỉ parse video_id rồi không dùng ID đó khi upsert;
checksum lấy raw_key thay vì hash nội dung. Không stat object để xác nhận đã upload,
không kiểm tra kích thước/đuôi file ở bước process, không ràng buộc key với ID cấp
ở presign. Cần validate key/ID và stat object trước khi tạo job.

Presign dùng endpoint `minio:9000` sẽ không truy cập được từ trình duyệt host.
Frontend thử direct upload trước, khi lỗi mới fallback multipart. Với local nên
dùng multipart trực tiếp hoặc cấu hình endpoint public + CORS đúng cho storage.
Fallback sau bước process lỗi cũng có nguy cơ upload lại cùng nội dung.

### 8. force reprocess không đảm bảo chạy lại

Route nhận `force=true`, nhưng `claim_video_ingestion()` không cho claim trạng thái
`indexed`, nên video đã index vẫn nhận 409. Ngược lại, allow_retry=True lại cho
claim cả `processing` và `deleting`, không ngăn job trùng hoặc đua với xóa video.

Ngay cả khi sửa claim để nhận indexed, route chưa truyền force vào worker/pipeline:
`run_ingestion_pipeline()` còn thoát sớm khi `ingested_at` đã có và model_version
không đổi. Cần sửa cả state transition lẫn ý định reindex xuống pipeline; không
cho phép claim processing/deleting như một retry bình thường.

### 9. Nhánh duplicate trả task cũ trong response

Upload/reprocess tạo record queued, gọi `update_task_status(...COMPLETED)` nhưng
trả lại object `record` ban đầu. `create_task_status()` trả Pydantic model độc lập;
không có cơ chế tự cập nhật object này khi status trong DB đổi.
Response trực tiếp có thể vẫn queued/0 dù polling sau đó completed/100.

### 10. Pipeline privacy chưa đúng mô tả YOLO

`default_dependencies()` chọn `LabelHeuristicDetector`, không phải YOLO.
`anonymize_frames()` gọi anonymize mà không truyền object labels; detector nhận
objects=None và trả vùng rỗng. `anonymize_frame()` vẫn báo blurred=True khi không
có vùng, khiến frame được đánh dấu verified dù không blur.

Không thể coi upload tùy ý đã được ẩn danh. `FullFrameDetector` có sẵn nhưng chưa
được chọn trong default pipeline; cần detector thực hoặc fallback rõ ràng.

### 11. Metadata mặc định có thể tạo kết quả filter sai

`app/pipelines/ingestion/indexer.py` khi thiếu VLM metadata gán mặc định clear/day/
residential, present car/road, absent night/rain. Thiếu quan sát không chứng minh
những nhãn đó. Cần để unknown/empty và đánh dấu degraded thay vì tự xác nhận/phủ
định nội dung. Vấn đề này không thể giải quyết bằng chỉnh similarity threshold.

### 12. Health và tài liệu/CI cũ tạo cảm giác sẵn sàng sai

`/health` luôn trả ok; startup nuốt lỗi từng backing service. Chỉ dùng endpoint
này làm liveness, cần readiness riêng nếu dùng để xác nhận toàn stack hoạt động.

Makefile có `deploy-only` định nghĩa hai lần; nhiều target gọi `scripts/` không
còn tồn tại. `docker-infra` được nhắc/khai báo PHONY nhưng không có recipe.
README vẫn có seed script, Cloud Run script/YAML đã mất, demo credentials/login
form không khớp API JSON email/password, và số test cũ.
CI lint gọi các đường dẫn đã mất (`agents`, `models`, `main.py`, `config.py`) và
chỉ cài dev, chưa cài media; mô tả tự deploy không khớp workflow hiện có.

## Bản đồ API và khả năng test khi chưa có video

| Nhóm | Quyền hiện tại | Có thể kiểm tra ngay | Còn cần chạy thật |
|---|---|---|---|
| `/health` | Public | HTTP contract | Không chứng minh dependency sẵn sàng |
| `/auth/*` | Login/register/refresh public; profile cần user; users cần admin | JWT, validation, role bằng mock | DB/Redis thật, bootstrap admin, revoke khi DB lỗi |
| `/search` | Public | Schema, cursor, filtering/fusion trên fixtures | Qdrant mới + encoder thật, chất lượng cần video/nhãn |
| `/chat` | Public | Schema/logic với stub VLM | LLM API và ảnh thật; local app hiện vẫn cần dịch vụ LLM bên ngoài |
| `/ingest/*`, `/tasks*`, DELETE `/videos/*` | Admin | Auth, enqueue, trạng thái và lỗi bằng stub | Object store + broker + worker, pipeline thật |
| `/media/*` | Optional auth | Range/404 bằng fixture | Chặn raw, derivative/seek/cache thật |
| `/datasets/export` | Engineer/admin | Manifest/ZIP fixture | File export và clip thực, giới hạn bộ nhớ |
| `/feedback/rerank` POST | Optional auth | Validation, persistence mock | DB thật; không nhầm với hook log prompt |
| `/feedback` list/stats/export | Admin | HTTP contract | Dữ liệu DB thật |
| `/admin/*` | Admin | Quyền, shape response | Telemetry thật; load/unload cả Qwen và SigLIP |

Integration pipeline hiện dùng stub repository/storage/encoder và fixture; test
qua không chứng minh tích hợp PostgreSQL/Redis/MinIO/Qdrant/GPU thật đã qua.

## Cấu hình cũ còn chờ duyệt

| Mục đề xuất | Thao tác sau khi được duyệt | Lý do |
|---|---|---|
| `Makefile` | Bỏ target Cloud Run/script mất và target trùng | Giữ các target local đang dùng |
| `README.md` | Dọn link/script triển khai đã mất | Giữ tài liệu còn hữu ích |
| `.github/workflows/ci.yml` | Sửa đường dẫn lint và extras/test/build | CI vẫn cần cho local development |
| `docker-compose.deploy.yml`, `deploy/README.md` | Có thể bỏ nếu xác nhận bỏ hẳn cấu hình shared VM | Còn có cấu hình Postgres/Redis tham khảo |

Không đề xuất xóa migrations, pyproject/lockfile, pyrightconfig, ruff config,
frontend/nginx hay Dockerfile.prod chỉ vì chuyển local. Chúng còn công dụng.
Không có cloudrun/cloudbuild YAML để xóa trong checkout này; chỉ còn tham chiếu cũ.

APM của ứng dụng (`app/core/tracer.py`, `/admin/traces`, UI Trace Explorer) và
feedback RLHF vẫn được giữ vì phục vụ giám sát hiệu năng và đánh giá kết quả.

## Thứ tự chuyển local đề xuất

1. Chốt danh sách cấu hình triển khai cũ ở trên trước khi dọn tiếp.
2. Hoàn chỉnh Compose local với đủ bốn backing services và volume riêng;
   `.env.example` cho local không trỏ cloud. Tạo admin local thực trong DB.
3. Sửa collection vector contract, auth fallback, preview/seek/delete và privacy.
4. Sửa direct upload, force reprocess, duplicate response và metadata unknown.
5. Chạy smoke test không cần video: migrations, register/login/profile/refresh,
   admin RBAC, task list rỗng, search corpus rỗng, backing service readiness.
6. Dùng clip synthetic ngắn để kiểm thử upload → worker → preview → search →
   export → delete. Sau đó dùng video thật để đánh giá nội dung và chất lượng.

Chạy trên máy local chưa đồng nghĩa offline: embeddings/model weights cần tải
lần đầu; chat/agentic/VLM metadata hiện gọi LLM bên ngoài. Muốn offline hoàn toàn
cần quyết định thêm mô hình/dịch vụ LLM local và khả năng VRAM.
