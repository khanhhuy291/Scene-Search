# Docker và GPU VM

Cấu hình hiện tại sử dụng một stack `docker-compose.yml` cho local và máy ảo GPU. Hướng dẫn lệnh, port, model readiness, dữ liệu ingestion và kiểm thử nằm tại [LOCAL_DOCKER.md](LOCAL_DOCKER.md).

## Triển khai lên VM

1. Cài Docker Compose và NVIDIA Container Toolkit trên VM, xác nhận CUDA hoạt động trong container.
2. Checkout source và cấu hình `app/.env` cho VM. Đặt các key/credential của VM trong env; giữ các tham số ingestion v3 cần thiết.
3. Chạy từ root repository:

```bash
make docker-up
# hoặc
docker compose --env-file app/.env up -d --build
```

4. Kiểm tra `docker compose --env-file app/.env ps`, model `/model/status` phải `ready`, rồi thử từng mode search qua UI/API.

Mặc định UI bind `127.0.0.1:5173`. Cấu hình `HTTP_BIND_ADDRESS` và `HTTP_PORT` theo cách truy cập VM hoặc reverse proxy của bạn. API, MinIO và Qdrant chỉ publish trên loopback; Postgres/Redis dùng Docker network nội bộ.

Named volumes nằm trên từng host. Dữ liệu local không tự xuất hiện trên VM; cần chuyển dữ liệu bằng quy trình riêng hoặc ingestion mới. Không xóa volume khi cập nhật code.

Các Compose local/deploy/CPU cũ đã được gom về file duy nhất. Alias Make deploy chỉ khởi động stack trên host hiện tại, không tự upload hay triển khai lên Cloud Run.
