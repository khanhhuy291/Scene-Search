# Rà soát API, file không dùng và cấu hình build

Ngày rà soát: 2026-11-12. Phạm vi: router FastAPI, nơi gọi trong frontend và
script, worker, pipeline, Makefile, Compose, Dockerfile, CI và cấu hình Python.
Đây là rà soát tĩnh trên source hiện tại; chưa chạy API, build hoặc test trong
đợt này. Chưa xóa file hoặc endpoint. Các thay đổi bên dưới chờ người dùng duyệt.

## 1. Luồng đang sử dụng

### Ingestion

Frontend `src/api/ingestion.js` hiện thử:

```text
POST /ingest/presigned-url
  → browser PUT trực tiếp vào object storage
  → POST /ingest/process
  → ghi nhận video trong PostgreSQL → Celery queue ingestion

Nếu luồng trên lỗi:
POST /ingest/upload (multipart)
  → lưu raw MinIO → ghi nhận video → Celery queue ingestion

worker/tasks/ingestion.py → pipelines/ingestion/orchestrator.py
  → đọc và kiểm tra video → lấy frame → lọc/gom cảnh
  → embedding và enrichment → thumbnail/playback derived
  → metadata PostgreSQL + vector/payload Qdrant

GET /tasks và GET /tasks/{task_id} → frontend theo dõi tiến độ
DELETE /videos/{video_id} → frontend xóa video
```

Script `app/scripts/bulk_ingest.py` dùng API ingestion; không phải file bỏ quên.
Worker caption refresh cũng được Celery đăng ký và chạy trên queue ingestion.

### Search và playback

```text
frontend/src/lib/searchApi.js → POST /search
  → phân tích query, agentic routing/HyDE nếu bật
  → retrieval/embedding và catalog caption
  → xử lý kết quả/rerank theo cấu hình
  → trả video_id + timestamp + thumbnail + URL playback
  → frontend phát video đầy đủ và giới hạn theo start/end của segment
```

`SEARCH_RERANK_ENABLED=true` là cấu hình cho phép rerank, không chứng minh model
reranker chạy thành công trong mọi runtime. Cần giữ xử lý fallback hiện có khi
dọn build image.

## 2. Các nhóm API và nơi sử dụng

Có 36 route trong `app/api/v1`, chia thành 8 router. Số này không tính health
route ở app chính, docs/OpenAPI và API nội bộ của embedding service.

| Router | Số route | Nơi sử dụng / nhận định |
|---|---:|---|
| auth | 10 | `frontend/src/api/auth.js`: login/register, token, profile, quản lý user. Giữ |
| admin | 9 | `frontend/src/api/admin.js`: telemetry, eval, model load/unload, traces; caption refresh dùng qua API quản trị. Giữ |
| chat | 1 | `frontend/src/api/chat.js` và ChatWidget. Giữ |
| datasets | 1 | `frontend/src/api/datasets.js`, xuất dataset ZIP. Giữ |
| feedback | 4 | `frontend/src/api/feedback.js`, UI thu thập và quản lý RLHF. Giữ |
| ingestion | 7 | Upload, task, delete, reprocess. Hai route direct upload có thể bỏ nếu đổi frontend sang multipart local |
| media | 3 | Thumbnail, clip theo point, full video theo video_id. Frontend và search response vẫn dùng các URL này. Giữ |
| search | 1 | API search chính. Giữ |

Không coi một API là thừa chỉ vì không có nút gọi trực tiếp trong UI: caption
refresh và reprocess là thao tác quản trị. Không coi module là thừa chỉ vì không
có import Python: API main, embedding API, bootstrap admin và các CLI là entrypoint.

Traces hiện tại có `core/tracer.py`, admin routes và TraceExplorer trong UI.
Đây là tính năng quan sát ứng dụng đang được nối vào project, khác với các hook
AI activity logging đã xóa trước đó. Nếu muốn bỏ traces, cần gỡ cả UI và các
chỗ ghi trace; không nên chỉ xóa admin route.

## 3. File đề xuất xóa sau khi duyệt

### Nhóm A — code không còn được runtime hiện tại gọi

| File | Bằng chứng | Thay đổi đi kèm |
|---|---|---|
| `frontend/src/components/auth/LoginCard.jsx` | Không tìm thấy import hoặc nơi dùng ngoài định nghĩa | Không có API cần bỏ; AuthPage/modal hiện xử lý đăng nhập |
| `frontend/src/components/auth/RegisterCard.jsx` | Không tìm thấy import hoặc nơi dùng ngoài định nghĩa | Không có API cần bỏ |
| `frontend/src/styles.css` | Không có import; app sử dụng `src/styles/main.css` | Giữ stylesheet đang được import |
| `app/search/hyde.py` | Không có import trong runtime; chỉ `tests/unit/test_agentic_search.py` dùng | Bỏ các test riêng cho implementation cũ trong file đó; giữ test agent/router còn dùng. HyDE hiện nằm trong `search/router.py` |

Kết luận có giới hạn: kiểm tra bằng AST/import và tìm tên trong repository,
không phải quan sát traffic production hay chứng minh không có client bên ngoài.

### Nhóm B — stack triển khai cũ

| File | Nhận định |
|---|---|
| `docker-compose.yml` | Stack cũ vẫn dùng frontend dev server và hạ tầng bên ngoài; các target Makefile cũ vẫn tham chiếu. Bỏ nếu chỉ giữ Docker local |
| `docker-compose.deploy.yml` | Stack shared host, Qdrant qua host gateway, khác local. Bỏ nếu không còn vận hành kiểu triển khai này |
| `frontend/Dockerfile` | Được Compose cũ dùng cho Vite dev server. Chỉ bỏ cùng Compose cũ; local dùng `Dockerfile.prod` |
| `deploy/README.md` | Hướng dẫn stack deploy cũ; cần bỏ hoặc thay nội dung nếu bỏ stack tương ứng |

Gỡ cùng các target Makefile và cập nhật tài liệu tham chiếu. Giữ
`deploy/local-minio/Dockerfile`: local đang build MinIO bằng file này.
Giữ `app/Dockerfile`, `frontend/Dockerfile.prod`, các lockfile, migrations và test.

### Nhóm C — hai API direct upload cho cloud

Đề xuất chỉ áp dụng nếu thống nhất upload local qua multipart:

- Bỏ `POST /ingest/presigned-url` và `POST /ingest/process` cùng request/response
  schema riêng trong `app/api/v1/ingestion.py`.
- Sửa `frontend/src/api/ingestion.js` để gọi `/ingest/upload` ngay.
- Rà nơi dùng `get_presigned_upload_url` trước khi bỏ helper MinIO và cập nhật test.
- Giữ giới hạn upload 500 MiB hiện tại và progress của frontend.

Lý do: presigned URL hiện ký với client MinIO nội bộ `minio:9000`, browser host
không có Docker DNS đó. Frontend local có thể phải thử direct upload thất bại rồi
mới fallback. Đây là suy luận từ source/config; chưa đo request trình duyệt trong
đợt rà soát này. Luồng direct upload còn dùng checksum bằng raw key thay vì SHA256
nội dung như multipart, làm hai đường xử lý dedup không thống nhất.

## 4. Các lỗi cấu hình/build cần sửa khi dọn

1. **Makefile trỏ tới script không tồn tại.** Thư mục root `scripts/` không có,
   nhưng nhiều target gọi `deploy-shared.sh`, `deploy-multicontainer.sh`,
   `deploy-gcp.sh`. `deploy-only` khai báo hai recipe nên recipe sau đè recipe trước.
   `.PHONY` còn `docker-infra` nhưng không có target implementation.
2. **CI lint sai đường dẫn.** `.github/workflows/ci.yml` tham chiếu `agents`,
   `models`, `main.py`, `config.py` trong `app/`, nhưng các đường dẫn này không có.
   Nên để CI gọi cùng lệnh lint do `app/Makefile` quản lý, bổ sung `scripts`
   vào tập source cần lint.
3. **Biến LLM mẫu không khớp settings.** `.env.example` có
   `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`; `LLMSettings` nhận `LLM_TIMEOUT`
   và không có field max_retries. Các biến mẫu đó không cấu hình được client
   hiện tại. Metadata extractor còn đặt timeout 30 giây riêng.
4. **Hai mẫu env và ba stack.** README cũ hướng dẫn mẫu env chung, tài liệu local
   dùng mẫu local. Nên chọn một mẫu env chính cho local, ghi rõ biến được Compose
   đặt, biến có thể override, biến bí mật và mặc định của Settings.
5. **Compose ghi cứng search flags.** Hai flag agentic/rerank là `true` trong
   `environment`, nên sửa cùng tên trong `.env` sẽ không thắng được giá trị này.
   Nên dùng interpolation để `.env` thực sự điều khiển flags.
6. **Phiên bản Python chưa thống nhất.** Docker/CI dùng 3.11; app Makefile tạo
   venv 3.12; pyproject type checker ghi 3.12 nhưng root pyrightconfig ghi 3.11.
   Cần chọn một phiên bản mục tiêu trước khi thay build.
7. **Build backend chưa theo lockfile.** Dockerfile cài từ pyproject, không dùng
   `requirements.lock`. Lock hiện còn dev/media dependency, chưa phải lock ML
   riêng. Không thể xóa lock hoặc áp chung cho GPU image một cách máy móc.
8. **Comment Dockerfile đã cũ.** Comment nói worker dùng ML extra, nhưng local
   worker/API dùng media và gọi embedding service riêng. Cập nhật comment cùng
   hướng dẫn thực tế.

## 5. Vấn đề API cần sửa, không nên giải quyết bằng xóa

- `reprocess?force=true` vẫn gọi `claim_video_ingestion` chỉ nhận trạng thái
  pending/failed/processing/deleting, không nhận indexed. Pipeline cũng trả
  duplicate nếu video đã ingest với cùng model version. Cần truyền được ý định
  force qua repository và worker nếu tiếp tục hỗ trợ re-index.
- `claim_video_ingestion(allow_retry=True)` nhận cả trạng thái processing, nên
  cần rà lại cơ chế chống hai task cùng xử lý một video.
- Upload direct kiểm tra định dạng video UUID nhưng lại lấy ID từ upsert theo
  raw_key; cần thống nhất contract nếu quyết định giữ luồng này.

## 6. Các module chưa thuộc luồng API chính nhưng chưa đề xuất xóa

- `app/ml/qwen_visual_reranker.py`: `app/eval/evaluate_qwen.py` vẫn import.
- `app/search/seed.py`: CLI hỗ trợ seed và có test riêng.
- `app/pipelines/ingestion/run_offline_ingestion.py` cùng `offline_embedder.py`:
  một luồng CLI ingestion từ caption JSONL khác với upload API. Chỉ bỏ nếu
  không còn nhu cầu ingest dữ liệu đã xử lý offline.
- `app/pipelines/summary/`: module summary có export và test; chưa thấy trong
  orchestrator upload hiện tại. Cần duyệt tính năng trước khi gỡ.
- `app/scripts/enrich_qdrant_concepts.py`, `migrate_legacy_media.py`: công cụ
  bảo trì dữ liệu; không có import runtime là bình thường đối với CLI.
- `ruff.toml` ở root và cấu hình Ruff trong pyproject: phạm vi áp dụng khác
  nhau. Chỉ hợp nhất sau khi chạy kiểm tra để tránh đổi rule ngoài ý muốn.

## 7. Kế hoạch sau khi được duyệt

1. Gỡ đúng các nhóm A/B/C được chọn; cập nhật chỗ gọi, test và tài liệu liên quan.
2. Hợp nhất đường vận hành local trong Makefile và mẫu env, sửa CI lint.
3. Kiểm tra import/router, lint, test liên quan auth/ingestion/search và parse
   Compose mà không in secret; không tự xóa volume hoặc dữ liệu đã ingest.
4. Nếu cần kiểm tra runtime/build GPU, báo riêng trạng thái đã chạy và kết quả.

Phạm vi duyệt xóa là source/config được liệt kê ở các nhóm, không bao gồm
`app/.env`, raw video, MinIO/Qdrant/PostgreSQL/Redis volumes hoặc model cache.

## 8. Rà soát mở rộng toàn project theo yêu cầu tiếp theo

Các nhóm A/B/C phía trên vẫn là đề xuất, chưa được thực hiện. Đợt mở rộng này
xét cả backend, frontend, schema, pipeline, CLI/eval, dependency và tài liệu.
Không thay source/build và chưa chạy test hoặc thay đổi dữ liệu.

### Phương pháp và giới hạn

- Lập đồ thị import bằng AST cho 131 module Python (không tính tests, venv/cache).
  Từ API main, Celery app/tasks và embedding API có 95 module được đi tới trong
  mô hình import tĩnh. Import có điều kiện và import typing vẫn được tính; đây
  không phải số module thực sự được load trong một process.
- Xét CLI/eval/bootstrap/migration như các entrypoint riêng để tránh kết luận
  nhầm file không được API import là file thừa.
- Đối chiếu JSX/JS/CSS với import, route và URL; đối chiếu dependency với source;
  tìm nơi đọc settings và nơi gọi các model/repository.
- So hash để xác nhận artifact trùng byte. Không đọc secret để đưa vào báo cáo.
- Không dùng số lần xuất hiện tên để kết luận một route FastAPI thừa: decorator
  và framework có thể gọi hàm mà không có caller Python trực tiếp.

### 8.1. Các mục mới có bằng chứng không được dùng trong source hiện tại

| Mục | Bằng chứng | Đề xuất cụ thể sau khi được duyệt |
|---|---|---|
| `app/pipelines/summary/summarizer.py` và `__init__.py` cùng thư mục | Ngoài import nội bộ package, caller chỉ có test trong `app/tests/unit/test_qwen_embedding.py`; API/worker/CLI hiện không gọi | Bỏ package summary và test riêng của nó; giữ test Qwen encoder. Caption VLM và embedding ingestion hiện tại không phụ thuộc package này |
| `clsx`, `tailwind-merge` trong `frontend/package.json` | Không thấy import trong source frontend | Gỡ hai dependency và cập nhật package-lock bằng npm |
| `ultralytics` trong ML extra ở `app/pyproject.toml` | Không thấy import `ultralytics` hoặc implementation YOLO trong source app; có comment về detector tùy chọn nhưng chưa có detector đó | Gỡ dependency khỏi extra; kiểm tra test packaging và dependency resolver. Không gỡ torch/transformers/open-clip/sentence-transformers đang dùng |
| `app/docker/minio/create-bucket.sh` | Không có Compose, Dockerfile, Makefile hoặc tài liệu hiện tại gọi script; API startup đã gọi ensure_bucket | Có thể bỏ script nếu không có quy trình vận hành ngoài repository dùng nó; xác minh chính sách anonymous riêng vì ensure_bucket không tương đương mọi lệnh trong script |
| `exporting` ở root | File rỗng | Có thể bỏ, không có chức năng runtime |

Các mục frontend không import và module HyDE cũ đã liệt kê ở nhóm A vẫn có
cùng bằng chứng. Chúng không phải toàn bộ phần dư của project.

### 8.2. Settings khai báo nhưng chưa thấy nơi đọc ngoài config

Đối chiếu source Python ngoài test/config cho thấy:

- `QdrantSettings.hnsw_ef_search`.
- `MLSettings.num_workers`.
- `VideoSettings.sampling_ssim_threshold`.
- `VideoSettings.preview_codec`.
- `VideoSettings.preview_fps` (comment đã ghi là legacy).
- `DatasetSettings.manifest_name`.

Đây là các ứng viên bỏ field/biến mẫu sau khi kiểm tra test và contract CLI.
Không suy ra sampler hoặc codec hiện tại thiếu chức năng: code có thể dùng giá
trị cố định thay vì field. Chẳng hạn thumbnail_max_edge/thumbnail_quality vẫn
được preview_generator đọc, nên phải giữ.

### 8.3. Schema và repository của thiết kế cũ

`app/db/models/review.py` chứa User đang dùng và các model cũ `ReviewSession`,
`ReviewDecision`, `Dataset`, cùng enum trạng thái/phán quyết. Các model cũ vẫn
được export qua `db/models/__init__.py`, nhưng không thấy service/API hiện tại
đọc ghi chúng. DatasetContext lưu bản nháp ở localStorage; API export đọc
Qdrant/catalog rồi tạo ZIP, không ghi model Dataset này.

Vì vậy không thể xóa nguyên `review.py` — auth dùng User trong file này. Có thể
tách User/UserRole ra file riêng và dọn phần review cũ, nhưng phải xử lý metadata,
test và lịch sử migration. Không drop bảng hoặc xóa migration cũ chỉ để giảm
số file; cần kiểm tra dữ liệu DB trước nếu muốn loại bỏ schema.

Trong `app/repositories/corpus.py`, các hàm `insert_frames`, `insert_frame_objects`,
`insert_frame_attributes`, `insert_behavior_events` và các row dataclass tương ứng
chưa có caller trong app ngoài định nghĩa/export. Orchestrator hiện lưu segments,
Qdrant payload và video assets. Đây là ứng viên dọn API repository, không có
nghĩa toàn bộ bảng Frame có thể bỏ: `mark_video_indexed` vẫn update Frame và model
relations/migrations vẫn tham chiếu nó.

### 8.4. Code có dùng nhưng có thể gom để giảm độ rối

- `tracker.py`: implementation mặc định PassthroughTracker chỉ `yield from`.
- `behavior_detector.py`: NoopBehaviorDetector cũng chỉ `yield from`.
- Cả hai vẫn được orchestrator và integration test dùng. Có thể bỏ bước trung
  gian hoặc gom các interface nếu quyết định chưa hỗ trợ tracking/behavior;
  không được xóa file mà không sửa PipelineDependencies và test injection.
- `anonymizer.py` và `privacy_verifier.py` có xử lý thật; không gộp nhầm vào các
  stage passthrough và không bỏ chỉ vì file ngắn.
- `minio_console.py` và các field `scene_media_*` phục vụ index/media remote;
  local mặc định không bật console adapter. Media router vẫn có nhiều nhánh đọc
  remote và tên host cũ. Có thể rút gọn thành storage local sau khi duyệt bỏ
  tương thích dữ liệu/index remote; đây là thay đổi tính năng, không phải dead code.

### 8.5. Giao diện và tài liệu có nội dung lặp/cũ

- `docs/architecture.html` và `frontend/public/architecture.html` trùng byte,
  mỗi file 750308 byte, SHA256 bắt đầu `4901fbb8b18c4934`. Frontend dùng bản public.
  Nên giữ một nguồn và có bước xuất/copy rõ ràng hoặc liên kết tài liệu tới bản
  public; không xóa bản public vì iframe/link kiến trúc đang dùng nó.
- `LandingPage.jsx` dài 2133 dòng, `EvaluationBenchmark.jsx` dài 1064 dòng.
  Cả hai chứa bảng benchmark/model/dataset với số liệu ghi cứng như Hit@5 89.77%.
  Chúng đang được render, không phải code không dùng. Nên đưa dữ liệu benchmark
  lịch sử về một file có provenance, chia component, và tách số liệu lịch sử khỏi
  kết quả đo corpus local hiện tại.
- `EvalPage.jsx` cũng gọi `/admin/eval`, trong khi tab live report của
  EvaluationBenchmark gọi cùng endpoint. Có thể dùng chung component/hook;
  hai nơi hiển thị không đồng nghĩa có thể xóa route frontend tùy ý.
- Có hai luồng evaluation: harness `app/eval/cli.py` và script
  `app/eval/evaluate_qwen.py` cùng tolerance metrics. Chúng có mục đích khác nhau,
  không thể coi toàn bộ `app/eval/` là thừa vì không có API import.
- Report ở root `eval/reports/` không phải file `/admin/eval` hiện đọc: endpoint
  tìm `reports/eval.json` và `app/eval/baselines/live.json`. Script compare còn
  chỉ định output `app/eval/reports/`. Cần thống nhất thư mục output và provenance;
  report cũ là artifact thí nghiệm, không tự động xóa.
- README/deploy guide/presentation chứa hướng dẫn cloud và số liệu lịch sử;
  LOCAL_DOCKER cũng có phần ghi nhận thời điểm corpus còn rỗng. Nên đánh dấu
  rõ lịch sử hoặc chuyển vào archive, giữ hướng dẫn vận hành hiện tại ngắn gọn.

### 8.6. Những phần đã xác định cần giữ

- Các entrypoint API, Celery worker, embedding API và bootstrap admin.
- Qwen encoder và SigLIP encoder, sampler/deduplicator/scene builder,
  metadata extractor, preview generator/indexer, caption refresh.
- Auth, search, media, dataset export, feedback và chat đang có UI/caller.
- Caption extraction thật không đi qua package summary nói trên.
- Các migrations là chuỗi lịch sử DB, không phải file dư chỉ vì tạo bảng cũ.
- Lockfiles là artifact tái lập dependency; config lint/test là công cụ phát triển.

### 8.7. Đợt dọn nhỏ đề xuất để duyệt độc lập

Đợt có phạm vi nhỏ gồm package summary (2 file), script create-bucket (1 file),
file root exporting (1 file), ba dependency không có import và các field settings
không được đọc ở 8.2. Trước khi áp dụng cần duyệt rõ từng mục; cập nhật lock/test
liên quan và chạy kiểm tra sau sửa. Đợt này không bao gồm A/B/C, không bỏ API,
không gỡ schema DB, không xóa report hoặc thay nguồn media remote.
