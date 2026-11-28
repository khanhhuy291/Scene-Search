# SceneSearch Docker local / GPU VM

Dùng duy nhất `docker-compose.yml`. Tất cả `make local-up`, `make docker-up` và các alias deploy đều trỏ tới cùng stack source-build. Project mặc định là `scenesearch-local`, giữ nguyên volume Postgres, Redis, MinIO, Qdrant, model cache và privacy weights.

## Khởi động

Giữ file `app/.env` hiện có; chỉ sao chép `app/.env.example` nếu chưa có cấu hình. Chọn model/device và collection trong env, không sửa logic search trong Compose.

```bash
make config-check PYTHON=/path/to/python
make docker-up
make local-admin
```

Lệnh tương đương:

```bash
docker compose --env-file app/.env up -d --build
docker compose --env-file app/.env ps
docker compose --env-file app/.env logs --tail 100 embedding-api api worker
```

- UI: http://localhost:5173; đổi `HTTP_PORT` nếu cần.
- API: http://localhost:8000, OpenAPI tại `/docs`.
- Embedding API: http://localhost:8001; kiểm tra `/model/status` với API key nếu đã cấu hình. `/health` có thể xanh trong lúc model đang tải; chỉ `state=ready` mới xác nhận sẵn sàng inference.
- MinIO console: http://localhost:9001; Qdrant: http://localhost:6333/dashboard.
- Postgres và Redis nằm trong Docker network, không publish port ra host.

`HTTP_BIND_ADDRESS` mặc định `127.0.0.1`. Để truy cập UI từ máy khác, cấu hình địa chỉ bind trong `app/.env` rồi recreate container frontend.

## Search và ingestion

Xem [hợp đồng ingestion/search trong README](../README.md#ingestion-v3--search). Năm mode là `siglip`, `qwen`, `caption`, `siglip_qwen_rrf`, `qwen_caption_rrf`.

```bash
curl -s http://localhost:5173/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"rainy street with cars","mode":"qwen_caption_rrf","limit":10,"explain":true}'
```

Caption được VLM sinh trong ingestion; Qwen text encoder tạo vector `caption` trong `scene_chunks`. Search không gọi VLM. Nếu corpus chỉ có schema legacy `scenes_local`, cần upload/re-ingest để tạo chunk/keyframe và publish ingestion mới; stack không tự chuyển đổi dữ liệu.

## Kiểm tra bản cập nhật 2026-11-28

- 103 test search/API/schema/RRF/evaluation/filter pass; 14 frontend test pass, ESLint/build/Ruff pass.
- Đã gọi năm mode qua Nginx/frontend: HTTP 200. Corpus local đang có 15 video legacy, 235 point trong `scenes_local`, chưa có publication v3, nên các lệnh này trả rỗng.
- Đã chạy `embed_frames`/`embed_frames_qwen`/`embed_scenes` với GPU thật và search cả năm mode bằng Qdrant in-memory: mỗi mode trả hai video fixture; kích thước vector là SigLIP 768, Qwen 2048, Caption 2048. Caption fixture là văn bản kiểm thử, không phải bằng chứng chất lượng retrieval hoặc VLM.
- Full suite hiện chưa xanh: hai file test ingestion import module đã bị xóa trước thay đổi này. Khi bỏ hai file đó, kết quả là 401 pass, 27 fail, 5 error, 2 skip. Đã kiểm tra snapshot HEAD gốc trong `/tmp`: các lỗi ngoài phạm vi search cũng có sẵn (media/dataset/catalog, schema/config ingestion, encoder/index/seed fixtures). Không sửa production ingestion để làm các test cũ xanh.

## Vận hành và giữ dữ liệu

```bash
make local-ps
make local-logs
make local-down
```

`local-down` dừng stack và giữ named volumes. Không dùng `down -v` khi muốn giữ corpus. Các container/volume thuộc dự án khác không bị thay đổi.

Nếu `nvidia-smi` thấy GPU nhưng CUDA không khởi tạo, kiểm tra lỗi model trước. Lần chạy trước đã có lỗi UVM trên host; khôi phục driver là việc riêng với cấu hình search. Không chuyển sang CPU hoặc đổi model một cách tự động.
