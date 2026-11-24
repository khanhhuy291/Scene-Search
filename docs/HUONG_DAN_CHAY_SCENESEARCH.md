# Chạy SceneSearch bằng Makefile

Chạy lệnh từ thư mục `code/Scene-Search`, nơi có [Makefile](../Makefile). Trên máy GTX 1650 4 GB, dùng `CPU=1` để chạy embedding bằng CPU.

Cập nhật code ngày 25/11/2026: ingestion cố định chia scene theo nội dung và thời gian (`content_time`), chọn thumbnail bằng medoid. Không còn cấu hình chọn `time`/`middle` hoặc fingerprint/snapshot cấu hình trong database, Qdrant và job Celery. Ngưỡng chia scene vẫn điều chỉnh qua `VIDEO_SCENE_*`; đổi cấu hình cần hoàn tất hoặc dọn job chờ trước khi khởi động lại API/worker. Video đã indexed được bỏ qua khi upload lại; dùng `force=true` ở API reprocess để xử lý lại.

Migration `20261122_0009` trong code chỉ còn thêm 3 cột vào `segments`: frame đại diện, timestamp đại diện và thumbnail key. Ngày 25/11/2026 đã đồng bộ PostgreSQL local đang ở revision này bằng một transaction gỡ đúng 8 cột dư thừa; giữ nguyên 3 cột cần dùng cùng 4 video, 48 segment và 5 task. PostgreSQL đã được dừng lại sau kiểm tra, API/worker chưa khởi động. Database mới chạy migrations bình thường. Với database khác đã áp dụng bản cũ của revision này, cần đối chiếu schema và gỡ 8 cột dư thừa trước khi sử dụng; `upgrade head` không tự chạy lại revision đã áp dụng.

## 1. Chuẩn bị

- Mở Docker Desktop ở chế độ Linux containers. Cài GNU Make trong môi trường terminal bạn dùng và kiểm tra bằng `make --version`. Nếu dùng WSL, bật Docker Desktop WSL Integration cho bản phân phối đang dùng.
- Đảm bảo có `app/.env`. Nếu cài trên máy mới, sao chép [app/.env.local.example](../app/.env.local.example) thành `app/.env` bằng trình quản lý file và thay mọi giá trị `change-me`. Mật khẩu admin cần ít nhất 12 ký tự và `AUTH_SECRET_KEY` cần ít nhất 32 ký tự.
- Lần đầu cần mạng để tải image, dependencies và model Qwen, SigLIP. Khi chạy CPU, model dùng RAM hệ thống và xử lý video chậm hơn.

Nếu PowerShell báo `make is not recognized` sau khi cài GnuWin32 Make, kiểm tra đường dẫn mặc định rồi thêm thư mục chứa `make.exe` vào `Path` của phiên hiện tại:

```powershell
$makeBin = 'C:\Program Files (x86)\GnuWin32\bin'
if (-not (Test-Path (Join-Path $makeBin 'make.exe'))) {
    throw 'Hãy kiểm tra vị trí cài GnuWin32 Make.'
}
$env:Path = "$makeBin;$env:Path"
make --version
```

Để dùng `make` trong các cửa sổ mới, thêm thư mục `$makeBin` vào biến `Path` của tài khoản Windows rồi mở lại PowerShell.

## 2. Khởi động và tạo admin

```sh
make local-up CPU=1
make local-ps CPU=1
```

`local-up` build image và chạy stack ở chế độ nền. API tự áp dụng Alembic migrations khi khởi động. Nếu API đang khởi động, theo dõi bằng `make local-logs CPU=1`. Nhấn `Ctrl+C` để thoát chế độ xem log.

Khi API báo `healthy`, chạy bước sau ở lần cài đầu tiên để tạo admin từ `LOCAL_ADMIN_EMAIL` và `LOCAL_ADMIN_PASSWORD` trong `app/.env`.

```sh
make local-admin CPU=1
```

Thông tin đăng nhập admin local đã cấu hình trong `app/.env`

- **Email** `admin@example.com`
- **Mật khẩu** `096ef9b69d700f41f29dafffeea61fbbffd9e1df7f3c09bf`

Nếu admin đã tồn tại và mật khẩu đã được đổi, dùng mật khẩu hiện tại của tài khoản.

Đăng nhập bằng tài khoản vừa tạo, mở **Ingestion** và chờ model báo **READY**. Sau đó tải lên một video MP4 ngắn, chờ job **Completed** và tìm thử trên trang **Search**.

## 3. Địa chỉ truy cập sau khi khởi động

| Dịch vụ | Địa chỉ | Dùng để |
| --- | --- | --- |
| SceneSearch Web | [http://localhost:5173](http://localhost:5173) | Mở trang chủ. |
| Đăng nhập | [http://localhost:5173/auth](http://localhost:5173/auth) | Đăng nhập bằng tài khoản local. |
| Ingestion | [http://localhost:5173/ingest](http://localhost:5173/ingest) | Xem trạng thái model, tải video và theo dõi job. |
| Search | [http://localhost:5173/search](http://localhost:5173/search) | Tìm cảnh trong video đã được xử lý. |
| Swagger UI | [http://localhost:8000/docs](http://localhost:8000/docs) | Xem và thử các endpoint của backend. |
| Backend health | [http://localhost:8000/health](http://localhost:8000/health) | Kiểm tra FastAPI có phản hồi. |
| Embedding health | [http://localhost:8001/health](http://localhost:8001/health) | Kiểm tra dịch vụ embedding có phản hồi. Xem **READY** ở trang Ingestion để biết model đã nạp xong. |
| MinIO Console | [http://localhost:9001](http://localhost:9001) | Xem bucket và file. Đăng nhập bằng `MINIO_ACCESS_KEY` và `MINIO_SECRET_KEY` trong `app/.env`. |
| MinIO API | [http://localhost:9000](http://localhost:9000) | Kết nối bằng công cụ tương thích S3. Kiểm tra tại [MinIO health](http://localhost:9000/minio/health/live). |
| Qdrant Dashboard | [http://localhost:6333/dashboard](http://localhost:6333/dashboard) | Xem collection và vector đã lập chỉ mục. |

Các địa chỉ này mở trên máy đang chạy Docker. PostgreSQL và Redis dùng mạng nội bộ của Docker. Nếu một trang chưa mở được, kiểm tra bằng `make local-ps CPU=1` và `make local-logs CPU=1`.

## 4. Các lệnh Make dùng hằng ngày

| Lệnh | Tác dụng |
| --- | --- |
| `make local-up CPU=1` | Build và khởi động stack local. Dùng khi chạy lần đầu hoặc sau khi đổi code đóng gói trong image, Dockerfile hay dependency. |
| `make local-build CPU=1` | Build image để dùng sau. |
| `make local-ps CPU=1` | Xem trạng thái container. |
| `make local-logs CPU=1` | Theo dõi log toàn stack, bắt đầu từ 100 dòng gần nhất của mỗi service. |
| `make local-admin CPU=1` | Tạo admin local. Nếu email đã thuộc admin, mật khẩu hiện tại vẫn dùng được. |
| `make local-down CPU=1` | Dừng stack và gỡ container cùng mạng Docker của project. |

Trên máy có GPU NVIDIA tương thích và đủ VRAM, bỏ `CPU=1` khỏi các lệnh `local-*` để dùng CUDA.

## 5. Dừng project và chạy lại

Chạy các lệnh dưới đây từ thư mục `code/Scene-Search`, cũng là nơi đã chạy lệnh khởi động.

### Dừng container và giữ lại để chạy tiếp

Nếu đã khởi động bằng `up -d --no-build`, dùng cùng cấu hình Compose để dừng:

```sh
docker compose --env-file app/.env -f docker-compose.local.yml -f docker-compose.local.cpu.yml stop
make local-ps CPU=1
```

Lệnh `stop` dừng các container nhưng giữ lại container, network và volumes. Để xem cả container đã dừng, chạy:

```sh
docker compose --env-file app/.env -f docker-compose.local.yml -f docker-compose.local.cpu.yml ps -a
```

### Dừng và gỡ container cùng network

```sh
make local-down CPU=1
make local-ps CPU=1
```

Lệnh Docker Compose tương đương với `make local-down CPU=1`:

```sh
docker compose --env-file app/.env -f docker-compose.local.yml -f docker-compose.local.cpu.yml down
```

Sau khi chạy `down` thành công, danh sách container local sẽ trống. Cả `stop` và `down` đều giữ dữ liệu trong volumes, bao gồm database, tài khoản admin, video và model cache. Không thêm `-v` hoặc `--volumes` vào `down` nếu muốn giữ dữ liệu.

`make local-ps CPU=1` chỉ xem trạng thái container, không khởi chạy dịch vụ. Nhấn `Ctrl+C` khi xem log chỉ thoát chế độ xem log; các dịch vụ chạy nền vẫn tiếp tục hoạt động.

### Khởi động nhanh bằng image đã build

Sau khi đã build thành công một lần, nếu code, Dockerfile và dependency vẫn như cũ, chạy:

```sh
docker compose --env-file app/.env -f docker-compose.local.yml -f docker-compose.local.cpu.yml up -d --no-build
make local-ps CPU=1
```

Lệnh này dùng lại image sẵn có, kể cả sau `make local-down CPU=1`. Dùng cùng lệnh nếu chỉ sửa `app/.env` để Compose áp dụng cấu hình mới. Nếu chỉ dùng `docker compose stop` và muốn bật lại các container đó với cấu hình cũ, có thể dùng:

```sh
docker compose --env-file app/.env -f docker-compose.local.yml -f docker-compose.local.cpu.yml start
```

Khi cần cập nhật image, dùng `make local-up CPU=1`. Nếu thay đổi chỉ nằm ở worker, có thể build riêng service đó:

```sh
docker compose --env-file app/.env -f docker-compose.local.yml -f docker-compose.local.cpu.yml up -d --build worker
```

## 6. Các nhóm lệnh Make khác

| Lệnh | Khi nào dùng |
| --- | --- |
| `make install`, `make install-ml` | Cài dependencies trên host. `install-ml` cài thêm PyTorch và các gói ML. Các target Python dùng môi trường Linux hoặc WSL. |
| `make backend`, `make worker`, `make frontend` | Chạy riêng API, Celery hoặc Vite trên host. API và worker cần hạ tầng mà host truy cập được. |
| `make migrate`, `make migration name=describe_change`, `make lock` | Áp dụng migration trên host, tạo revision mới hoặc cập nhật lockfile Python. |
| `make lint`, `make test`, `make quality` | Kiểm tra lint, chạy test hoặc chạy cả lint, test và build frontend. |
| `make frontend-lint`, `make frontend-test`, `make frontend-build` | Kiểm tra hoặc build riêng frontend. |
| `make eval-dry`, `make eval`, `make eval-check`, `make eval-qwen` | Các lệnh đánh giá retrieval. Xem tham số trong [hướng dẫn eval](../app/eval/README.md). |
| `make dev`, `make docker-up`, `make docker-down`, `make docker-ps`, `make docker-logs` | Vận hành stack từ `docker-compose.yml`, cần cấu hình hạ tầng bên ngoài. |
| `make docker-api`, `make docker-worker`, `make docker-embedding`, `make docker-frontend` | Build và khởi động từng service của stack từ `docker-compose.yml`. |
| `make deploy-compose`, `make deploy-vm`, `make docker-deploy`, các target `deploy*` còn lại | Triển khai server hoặc cloud. Xem [tài liệu deploy](../deploy/README.md). |

`make docker-infra` hiện chỉ được khai báo trong `.PHONY` và thiếu recipe. Để khởi động cả ứng dụng và hạ tầng local, dùng `make local-up CPU=1`.
