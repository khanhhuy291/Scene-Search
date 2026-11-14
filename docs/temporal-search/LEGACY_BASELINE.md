# A1 — Hiện trạng luồng cũ

## Phạm vi được bảo vệ

Baseline tham chiếu working tree, không chỉ nội dung ở commit. HEAD lúc khảo sát
là `b7b2c8ccb2b8e06f9f8041340c2732999462ea6c`.
Snapshot SHA-256 bao phủ 341 file hiện có, gồm `make.ps1` chưa tracked và những
file đã chỉnh trước đó. Không lưu nội dung source hay `.env` vào snapshot.

Các thay đổi đã có trước nhóm A gồm Makefile, README, Dockerfile, cấu hình Qwen,
test Qwen, Compose local và tài liệu vận hành. Nhóm A giữ chúng nguyên trạng.

## Luồng đã xác nhận từ source

| Bước | Source | Hành vi |
| --- | --- | --- |
| Entry point | `app/api/main.py`, `app/api/v1/__init__.py` | FastAPI, API version `/api/v1` |
| Nhận query | `app/api/v1/search.py::search_scenes` | `POST /api/v1/search`, chuyển request vào engine |
| Schema | `app/schemas/search.py` | Query tối đa 1000 ký tự, limit 1–100; `mode` chọn tower |
| Search | `app/search/engine.py::search` | Parse, lấy ứng viên, lọc, gom video, có nhánh agentic/rerank theo cấu hình |
| Gom video | `app/search/engine.py::_group_by_video` | Một kết quả/video; ưu tiên khả năng render khi chọn frame đại diện, sau đó điểm |
| Response | `app/api/v1/search.py::_to_result` | `matched_moments`, `total` đếm video, `total_keyframes` là số riêng |
| Media | `app/api/v1/media.py` | Thumbnail và playback qua API theo point ID, hỗ trợ Range |
| Frontend | `frontend/src/lib/searchApi.js`, `SearchPage.jsx`, `SceneCard.jsx` | Gọi API cũ, map các moment và seek/play |

`mode` hiện có `hybrid`, `visual`, `caption`, `qwen`, `siglip`. Không thêm
`temporal` vào enum này. Endpoint mới thuộc service mới.

## Ingestion và ý nghĩa scene

`orchestrator.py` lấy mẫu, xử lý frame, tạo embedding, gom scene, tạo media rồi
persist/index. `scene_builder.py::build_scenes` gom theo thời gian/gap, không
phải thuật toán dự đoán ranh giới theo query. Giá trị mặc định ở hàm là scene
tối đa 5 giây và gap 2 giây; chưa xác nhận giá trị hiệu lực trong runtime hiện tại.

`embedder.py::embed_scenes` lấy trung bình và chuẩn hóa các vector keyframe.
Các vector scene này đã mất chuỗi frame đầy đủ, không dùng thay đặc trưng CLIP
theo thời gian cho checkpoint grounding. `indexer.py` ghi point loại `segment`
với `video_id`, `ts_start_s`, `ts_end_s`.

Ảnh đại diện là thumbnail của scene. Một điểm tìm kiếm không đồng nghĩa chỉ có
một frame đã được mã hóa, và frame không đồng nghĩa scene.

## Những giới hạn tích hợp cần giữ đúng

1. API cũ trả kết quả đã lọc và gom video. `matched_moments` không phải toàn bộ
   top-N ANN thô. `total_keyframes` cũng không được đổi tên thành số ANN đã quét.
2. `indexer.py` có fallback metadata/caption, ví dụ `residential`, `clear`,
   `day` và `Dashcam driving scene at ...`. Những giá trị này không tự trở thành
   ground truth để chấm chất lượng hoặc thêm bộ lọc chặt vào nhánh mới.
3. `preview_generator.py` tạo một `videos/<video_id>/playback.mp4` đầy chuyển động
   cho toàn video rồi gán cùng key cho các scene. Source ghi rõ playback giữ
   hình ảnh nguồn. Đây không phải video dựng từ các frame lấy mẫu đã xử lý.
4. Một số chú thích schema/media nói media luôn đã ẩn danh. Điều đó mâu thuẫn
   với generator hiện tại. Nhóm A ghi nhận, không sửa hành vi cũ hoặc khẳng định
   mọi object trong bucket derived đều đã ẩn danh.
5. `/media/clip/<point_id>` là locator theo scene, không chứng minh file đó đã
   cắt riêng scene. Timestamp phải đối chiếu với origin của media thực.
6. Search router không khai báo dependency đăng nhập bắt buộc; media dùng
   `get_current_user_optional`. Không giả định đang có ACL theo video đã được
   kiểm chứng. Adapter mới phải chuyển tiếp ngữ cảnh caller, không tự dùng tài
   khoản admin để mở rộng phạm vi hoặc bỏ qua kiểm tra upstream.

## Cấu hình đã đọc từ Compose

Project `scenesearch-local`, API `127.0.0.1:8000`, embedding `8001`, frontend
`5173`, Qdrant `6333`. PostgreSQL/Redis chỉ nằm trong network Docker của stack.
Compose khai báo search mặc định `qwen`, collection `scenes_local`, Qwen 2048
chiều và bật cờ agentic/rerank. Việc cờ bật không chứng minh các model phụ đã
load hoặc đã tạo cải thiện. Không đọc hay đưa credential `.env` vào báo cáo.

## Lần khảo sát đầu ngày 14/11/2026, trước khi Docker được bật

- Docker daemon không truy cập được, không có bằng chứng container đang chạy.
- API `127.0.0.1:8000/health` không truy cập được.
- GPU GTX 1650 Max-Q, 4096 MiB, driver 621.14; lúc đo báo dùng 0 MiB.
- Dung lượng trống quan sát C khoảng 16,60 GiB, D 16,83 GiB, E 15,62 GiB.
- Các con số 1000 video/16569 segment đã ghi nhận ở phiên trước không được coi
  là kiểm kê live cho lần khảo sát này.

Không chụp được response search, OpenAPI runtime hoặc latency khi API đang tắt.
Python mặc định 3.9.10, chưa có pytest trong interpreter này. Backend yêu cầu
Python >=3.11. Không cài thêm dependency hoặc tự bật stack chỉ để sửa trạng thái
baseline. Chưa chạy suite backend trong nhiệm vụ này.

## Bổ sung sau khi người dùng bật Docker

Đã kiểm tra lại ngày 14/11/2026. Không khởi động lại, build hay thay đổi service.

- Cả 8 container của `scenesearch-local` đang chạy. Các container có healthcheck
  gồm API, embedding, MinIO, PostgreSQL, Redis đều healthy; các container khác
  báo running, không suy diễn có healthcheck.
- API `/health`, embedding `/health` và frontend đều trả HTTP 200.
- Model status sau các query báo `ready`, Qwen3-VL-Embedding-2B, vector 2048,
  `error=null`, GPU allocated khoảng 1881,5 MiB.
- Qdrant `scenes_local` green, 16569 points và 30114 indexed vectors. Số vectors
  không được dùng thay số scene vì collection có named vectors.
- HEAD và nội dung 341 file baseline vẫn nguyên trạng.

| Query mẫu | HTTP | Video trả về | Thời gian client quan sát |
| --- | --- | --- | --- |
| `dashcam driving scene` | 200 | 5 video khác nhau | 39630,60 ms |
| `a pedestrian crossing the road` | 200 | 0 | 885,28 ms |
| `a car changes lanes` | 200 | 5 video khác nhau | 439,11 ms |

Cả ba response khớp `SearchResponse` trong OpenAPI runtime. Các video không
trùng ID và các khoảng thời gian chính có thứ tự đúng. Query người đi bộ có
`below_threshold=true`, `unconfirmed_concepts=["people"]`, `degraded=false`.
Đây là hành vi quan sát được, không chứng minh kho không có người đi bộ.
Hai query có kết quả báo signals qwen/rerank; trường signals không tự chứng
minh reranker đã nâng chất lượng hoặc thực sự load thành công model phụ.

Một kết quả của query đầu được kiểm tra media. Thumbnail trả HTTP 200,
`image/jpeg`, header JPEG đúng. Playback trả HTTP 206 cho `bytes=0-1023`,
`video/mp4`, Content-Range `bytes 0-1023/21164562`. Chưa xem/chấm nội dung video,
chưa đo sai lệch timestamp bằng decode, và chưa kiểm tra toàn bộ media trong kho.

Query đầu chậm khoảng 39,6 giây, hai query sau dưới 1 giây. Không kết luận nguyên
nhân hoặc tính p95/cold-warm từ ba query khác nhau; benchmark có kiểm soát thuộc
nhóm B/E. Không chạy thêm query lặp lại chỉ để tạo con số tốc độ đẹp hơn.

Snapshot cuối là `data/temporal-search/group-a/baseline-live-verified-20261114.json`.
Snapshot live đầu có probe Docker unavailable vì tool thiếu quyền named-pipe,
trong khi API vẫn hoạt động. File cuối giữ nguyên response và bổ sung Docker
status từ phép đọc có quyền, ghi rõ provenance; không sửa snapshot cũ.
`media-check-20261114.json` lưu kết quả media. Không lưu header auth/credential.

Đã hoàn tất baseline live mẫu của A1. Suite pytest backend và đánh giá semantic
vẫn chưa được chạy trong lần kiểm tra này.

## Quy trình đối chiếu

`temporal-search/tools/legacy_baseline.py capture` ghi checksum, git status, HEAD,
probe health/OpenAPI, Docker, GPU và các query nếu yêu cầu và API sẵn sàng.
Tên snapshot mới là bắt buộc để không ghi đè baseline trước.

`verify` so SHA-256 với snapshot và phát hiện file cũ thay đổi, mất, file mới
ngoài hai vùng nhánh temporal hoặc HEAD thay đổi. Đây là kiểm tra bảo toàn
nguồn, không phải kiểm tra độ đúng semantic của model hay trạng thái database.

Khi có live snapshot, so cấu trúc, video IDs, timestamps và degraded flags với
cùng dữ liệu/config. Không yêu cầu `took_ms`, trace ID, cursor hoặc thứ hạng ANN
luôn giống từng byte. Dùng `test_search_endpoint.py`, `test_search_schema.py`
và các test engine/index hiện có khi môi trường Python 3.11+ sẵn sàng.
