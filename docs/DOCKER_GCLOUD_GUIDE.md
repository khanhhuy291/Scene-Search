# Một Docker Compose cho local và GCP GPU VM

Cấu hình duy nhất: `docker-compose.yml`. Cả hai môi trường build image từ source
trên chính máy chạy. Cần Linux, GPU NVIDIA, driver, Docker Compose v2 và NVIDIA
Container Toolkit. Đây là triển khai trên Compute Engine VM.

## Máy mới

Clone repo, copy `app/.env.example` sang `app/.env`, thay mọi giá trị
`change-me`, rồi chạy từ thư mục gốc:

```bash
make docker-up
make local-admin
make docker-ps
```

Máy local mở http://localhost:5173. Trên GCP VM đặt trong `app/.env`:

```dotenv
HTTP_BIND_ADDRESS=0.0.0.0
HTTP_PORT=5173
APP_ENV=production
APP_CORS_ORIGINS=http://YOUR_VM_IP:5173
```

Cho phép cổng HTTP đã chọn trong firewall VM/VPC, mở `http://YOUR_VM_IP:5173`.
Nếu dùng HTTPS, đặt reverse proxy TLS trước cổng frontend và đổi origin tương ứng.
Frontend gọi `/api/v1` cùng origin; Nginx chuyển tới `api:8000`. Không cần rebuild
frontend để thay IP VM. API, MinIO, Qdrant và embedding chỉ publish loopback;
PostgreSQL/Redis chỉ có trong mạng Docker. Upload qua API, tối đa 500 MiB;
Nginx cho phép request 512 MiB để chứa multipart overhead.

## Vận hành và dữ liệu

```bash
make docker-logs
make docker-down
make deploy-gcp
```

`deploy`, `deploy-gcp`, `docker-deploy`, `local-up` đều dùng cùng Compose;
`deploy-only` khởi động image đã build. Không có bước push registry/Cloud Run.
Project mặc định vẫn là `scenesearch-local` để giữ liên kết volume hiện có.
Máy mới tạo volume riêng; không tự sao chép dữ liệu từ local lên GCP.
Muốn đổi `COMPOSE_PROJECT_NAME`, cần chủ động chuyển dữ liệu trước.
Không dùng `down -v` nếu muốn giữ DB, video, vector và cache model.

API chạy migration rồi mới healthy; worker và frontend đợi API. Embedding health
chỉ là liveness: admin cần load model qua giao diện; xem `/model/status` trong
embedding service để biết model sẵn sàng. Search/ingestion có thể chưa chạy khi
model chưa load. `make docker-up` build/recreate dịch vụ; kiểm tra log sau cập nhật.

## Quy tắc cấu hình

- Chỉ có một template backend: `app/.env.example`; cấu hình thực tế là `app/.env`.
  Frontend có template riêng cho biến build `VITE_*`, không chứa secret backend.
- App đọc `app/.env` theo vị trí source, không phụ thuộc thư mục chạy Python.
  Biến môi trường của tiến trình có ưu tiên cao hơn dotenv, rồi mới đến default code.
- Compose chỉ override tuyến mạng nội bộ: PostgreSQL, Redis/Celery, MinIO,
  Qdrant và embedding. Vì vậy sửa URL native-host không chuyển các container sang
  dịch vụ ngoài. Các tùy chọn search, collection, timeout, model, dtype, bucket,
  CORS và debug lấy trực tiếp từ `.env` qua `env_file`.
- Ngoại lệ batch được đặt tên rõ: `ML_BATCH_SIZE` cho request API/worker;
  `QWEN_EMBEDDING_BATCH_SIZE` cho `ML_BATCH_SIZE` trong GPU embedding service.
  Embedding service luôn xóa URL remote của chính nó để tránh gọi vòng lại.
- PostgreSQL user/database vẫn là `scenesearch` để khớp volume hiện có. Đổi password
  trong env không tự đổi password đã lưu trong PostgreSQL; cần chủ động đổi trong DB.
- Native Python dùng các URL host trong `.env`; cần tự có các dịch vụ mà host truy cập
  được. Compose không publish PostgreSQL/Redis lên host theo mặc định.

Kiểm tra tên biến lạ/trùng và kiểu dữ liệu mà không in secret:

```bash
make config-check
# Nếu dùng môi trường Python khác:
make config-check PYTHON=/absolute/path/to/python
```

Lệnh này cần backend dependencies đã cài, không thử kết nối hạ tầng hay chạy model.
`docker compose config --quiet` kiểm tra cấu hình Compose; tránh chia sẻ output
`docker compose config` không có `--quiet` vì có thể chứa credential đã resolve.
Sau khi sửa env, `make docker-up` recreate container với cấu hình mới. `restart`
đơn thuần không nạp lại environment của container. Native process cần khởi động lại
vì `get_settings()` có cache.
