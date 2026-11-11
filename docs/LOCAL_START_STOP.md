# Khởi động và tắt SceneSearch local

Tài liệu này dành cho stack Docker local trong `docker-compose.local.yml`, có
Compose project `scenesearch-local`. Không dùng các lệnh `docker-up` hoặc
`docker-down`: các target đó trỏ tới stack cũ.

## 1. Điều kiện trước khi chạy

- Đã cài Docker Engine và Docker Compose plugin.
- Để embedding chạy bằng GPU: NVIDIA driver và NVIDIA Container Toolkit hoạt động
  trên host. Stack hiện cấu hình service `embedding-api` dùng CUDA.
- Đang ở thư mục gốc repository `Scene-Search`.
- Có `app/.env`. Khi cài mới, tạo file từ mẫu local:

  ```bash
  cp app/.env.local.example app/.env
  chmod 600 app/.env
  ```

- Mở `app/.env`, thay mọi `change-me` bằng giá trị riêng. Giữ lại các biến đã
  được cấu hình trên máy đang chạy, đặc biệt `LLM_API_KEY` nếu dùng NVIDIA VLM,
  và không commit file `.env`.

Stack bind các cổng local sau: web `5173`, API `8000`, embedding `8001`, Qdrant
`6333`, MinIO API `9000` và MinIO Console `9001`. PostgreSQL và Redis chỉ được
truy cập bên trong Docker network.

## 2. Khởi động lần đầu

Từ thư mục gốc repository:

```bash
make local-up
```

Lệnh này build image còn thiếu, tạo các container và chạy nền. Lần đầu có thể
mất nhiều thời gian vì cần tải dependency, PyTorch/CUDA và model weights. Lệnh
chỉ kết thúc khi Docker đã nhận yêu cầu khởi động; embedding model có thể vẫn đang
được tải hoặc nạp vào GPU.

Theo dõi trạng thái:

```bash
make local-ps
make local-logs
```

Trong log, đợi API hoàn tất Alembic migration và worker khởi động. Embedding API
có thể báo healthy trước khi model sẵn sàng; chờ log model hoặc kiểm tra trạng
thái model trong Admin/API. Khi cần xem riêng một service:

```bash
docker compose --env-file app/.env -f docker-compose.local.yml logs -f --tail=100 embedding-api
```

Tạo tài khoản admin local sau khi API đã healthy:

```bash
make local-admin
```

Lệnh dùng `LOCAL_ADMIN_EMAIL` và `LOCAL_ADMIN_PASSWORD` trong `app/.env`. Có thể
chạy lại; nếu user đã tồn tại thì bootstrap không đổi mật khẩu hiện tại.

Mở ứng dụng:

- Web: <http://localhost:5173>
- Swagger API: <http://localhost:8000/docs>
- MinIO Console: <http://localhost:9001>
- Qdrant dashboard: <http://localhost:6333/dashboard>

## 3. Khởi động ở những lần tiếp theo

Sau khi máy đã tắt stack bằng `make local-down`, chạy lại:

```bash
make local-up
make local-ps
```

Docker giữ dữ liệu PostgreSQL, Redis, MinIO, Qdrant và model cache trong named
volumes. Không cần upload lại video chỉ vì đã dừng hoặc khởi động lại container.
Nếu sửa source code và muốn build lại image, `make local-up` cũng build lại theo
cấu hình Compose.

## 4. Kiểm tra nhanh sau khi khởi động

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:9000/minio/health/live
make local-ps
```

`/health` của embedding chỉ kiểm tra liveness của service, không xác nhận model
đã sẵn sàng. Nếu model chưa ready, ingestion/search có thể lỗi dù container đang
chạy. Xem log riêng:

```bash
docker compose --env-file app/.env -f docker-compose.local.yml logs --tail=150 embedding-api
```

## 5. Xem log và khởi động lại từng service

Theo dõi log toàn stack bằng `make local-logs`; nhấn `Ctrl+C` chỉ thoát chế độ
xem log, không dừng container.

Xem log một service:

```bash
docker compose --env-file app/.env -f docker-compose.local.yml logs -f --tail=100 api
```

Thay `api` bằng `worker`, `embedding-api`, `frontend`, `postgres`, `redis`,
`minio` hoặc `qdrant` khi cần.

Khởi động lại một service mà không dừng phần còn lại:

```bash
docker compose --env-file app/.env -f docker-compose.local.yml restart api
```

Sau khi thay đổi cấu hình Compose hoặc cần tạo lại container frontend để cập nhật
kết nối tới API:

```bash
docker compose --env-file app/.env -f docker-compose.local.yml up -d --no-deps --force-recreate frontend
```

## 6. Dừng project

Để dừng toàn bộ container nhưng giữ dữ liệu và model cache:

```bash
make local-down
```

Đây là cách dừng thông thường. Lần sau dùng `make local-up` để chạy lại. Nếu chỉ
cần dừng tạm một service:

```bash
docker compose --env-file app/.env -f docker-compose.local.yml stop embedding-api
```

Chạy `start` để bật lại service đã stop:

```bash
docker compose --env-file app/.env -f docker-compose.local.yml start embedding-api
```

Hoặc dùng `make local-ps` để kiểm tra stack sau khi dừng. Lệnh `make local-down`
không xóa named volumes.

## 7. Những lệnh cần phân biệt

| Lệnh | Tác dụng |
|---|---|
| `make local-up` | Build nếu cần và chạy stack local ở chế độ nền |
| `make local-build` | Chỉ build image, không khởi động container |
| `make local-logs` | Theo dõi log; `Ctrl+C` không dừng stack |
| `make local-down` | Dừng và gỡ container/network của stack, giữ named volumes |
| `make local-ps` | Xem trạng thái container local |
| `make docker-up` / `make docker-down` | Target của cấu hình cũ; không dùng cho stack local này |

Không thêm `-v` vào lệnh `docker compose down` khi cần giữ dữ liệu. Xóa volume
có thể xóa database, video trong MinIO, Qdrant vectors và model cache.

## 8. Khắc phục sự cố thường gặp

### API hoặc web chưa truy cập được

```bash
make local-ps
docker compose --env-file app/.env -f docker-compose.local.yml logs --tail=150 api frontend
```

Đợi PostgreSQL/Redis/MinIO healthy và API hoàn tất migration. Nếu container vừa
được tạo lại nhưng trình duyệt nhận `502`, tạo lại frontend để Nginx phân giải
lại địa chỉ API:

```bash
docker compose --env-file app/.env -f docker-compose.local.yml up -d --no-deps --force-recreate frontend
```

### Embedding báo lỗi CUDA

Xem log GPU:

```bash
docker compose --env-file app/.env -f docker-compose.local.yml logs --tail=200 embedding-api
```

Nếu báo CUDA launch failure hoặc lỗi GPU sticky, dừng ingestion, sau đó làm theo
mục “Khôi phục lỗi CUDA” trong [LOCAL_DOCKER.md](LOCAL_DOCKER.md). Đừng tiếp tục
gửi batch video vào embedding process đang lỗi.

### Đổi `.env`

Thay đổi `.env` không tự cập nhật môi trường của container đang chạy. Tạo lại
service cần nhận biến mới, ví dụ:

```bash
docker compose --env-file app/.env -f docker-compose.local.yml up -d --no-deps --force-recreate api worker
```

Nếu thay biến dùng chung hoặc không chắc service nào phụ thuộc, chạy lại toàn bộ
stack bằng `make local-up`.

## Tham khảo

- [Hướng dẫn Docker local và cấu hình](LOCAL_DOCKER.md)
- [Ingest hàng loạt video](BULK_INGEST.md)
- [Layout video playback và derived](VIDEO_PLAYBACK.md)
