# CẨM NANG HƯỚNG DẪN DOCKER & GOOGLE CLOUD (GCLOUD)
> **Dự án**: SceneSearch (P-081) - Semantic Video Search Platform  
> **Cập nhật gần nhất**: 2026-08-26  

---

## MỤC LỤC
1. [Kiến trúc Microservices của SceneSearch](#1-kiến-trúc-microservices-của-scenesearch)
2. [Cẩm nang lệnh Docker thiết yếu](#2-cẩm-nang-lệnh-docker-thiết-yếu)
3. [Cẩm nang lệnh Google Cloud CLI (gcloud)](#3-cẩm-nang-lệnh-google-cloud-cli-gcloud)
4. [Quy trình đóng gói & đẩy lên GCP Artifact Registry](#4-quy-trình-đóng-gói--đẩy-lên-gcp-artifact-registry)
5. [Hai phương án triển khai hệ thống (Deploy)](#5-hai-phương-án-triển-khai-hệ-thống-deploy)
   - [Phương án A: Máy ảo GPU (GCE VM) + Docker Compose (Khuyên dùng)](#phương-án-a-máy-ảo-gpu-gce-vm--docker-compose-khuyên-dùng)
   - [Phương án B: Serverless (Cloud Run + GCS + Qdrant Cloud)](#phương-án-b-serverless-cloud-run--gcs--qdrant-cloud)
6. [Bảng tra cứu lỗi thường gặp & Cách khắc phục (Troubleshooting)](#6-bảng-tra-cứu-lỗi-thường-gặp--cách-khắc-phục-troubleshooting)

---

## 1. KIẾN TRÚC MICROSERVICES CỦA SCENESEARCH

Hệ thống được thiết kế theo chuẩn **Microservices độc lập**, bao gồm **4 Service mã nguồn tự phát triển** và **4 Dịch vụ dữ liệu/hạ tầng**:

```
                              [ Google Cloud Load Balancer / Ingress (Port 80/443) ]
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    │ (Path: /)                                     │ (Path: /api/v1/*)
                    ▼                                               ▼
        ┌───────────────────────┐                       ┌───────────────────────┐
        │  Frontend Service     │                       │  API Gateway Service  │
        │  (React + Nginx)      │                       │  (FastAPI)            │
        │  Port: 80 / 8080      │                       │  Port: 8000           │
        └───────────────────────┘                       └───────────┬───────────┘
                                                                    │
                         ┌──────────────────────────────────────────┼───────────────────────┐
                         │ (Inference RPC)                          │ (Task Queue)          │ (Async Engine)
                         ▼                                          ▼                       ▼
             ┌───────────────────────┐                  ┌───────────────────────┐     ┌───────────────────┐
             │  ML Embedding Service │                  │  Celery Worker        │     │  PostgreSQL       │
             │  (Qwen3-VL GPU Node)  │                  │  (Video Ingestion)    │     │  Port: 5432       │
             │  Port: 8001 (GPU)     │                  │  (FFmpeg + PyAV)      │     └───────────────────┘
             └───────────────────────┘                  └───────────┬───────────┘
                                                                    │                 ┌───────────────────┐
                                                                    ├───────────────> │  Redis            │
                                                                    │                 │  Port: 6379       │
                                                                    ▼                 └───────────────────┘
                                                        ┌───────────────────────┐
                                                        │  Qdrant Vector DB     │     ┌───────────────────┐
                                                        │  (HTTP: 6333,         │     │  Google Storage   │
                                                        │   gRPC: 6334)         │     │  (Thay thế MinIO) │
                                                        └───────────────────────┘     └───────────────────┘
```

| Microservice | Công nghệ | Cổng (Port) | Nhiệm vụ |
|---|---|---|---|
| **`frontend-service`** | React, Vite, Nginx | `80` (Compose) / `8080` (Cloud Run) | Giao diện tìm kiếm, xem video, duyệt dataset, admin |
| **`api-service`** | FastAPI, Python 3.11 | `8000` | Điều phối tìm kiếm (Agentic Search), Auth JWT, Streaming Proxy |
| **`worker-service`** | Celery, PyAV, FFmpeg | *Không mở port ngoài* | Nạp video ngầm, cắt cảnh, trích xuất frame |
| **`ml-service`** | FastAPI, PyTorch (CUDA) | `8001` (Cần GPU) | Trích xuất vector đa phương thức (Qwen3-VL 2048d, SigLIP 768d) |

---

## 2. CẨM NANG LỆNH DOCKER THIẾT YẾU

### 2.1. Quản lý Image (Đóng gói mã nguồn)
* **Build Image từ Dockerfile**:
  ```bash
  docker build -t <TÊN_IMAGE>:<TAG> <ĐƯỜNG_DẪN_THƯ_MỤC>
  ```
  *Ví dụ build Backend*:
  ```bash
  docker build --build-arg EXTRAS=media -t api-service:v1 ./app
  ```
* **Xem danh sách Image hiện có trên máy**:
  ```bash
  docker images
  ```
* **Đổi tên / Gắn thẻ Image chuẩn GCP**:
  ```bash
  docker tag api-service:v1 asia-southeast1-docker.pkg.dev/<PROJECT_ID>/scenesearch-repo/api-service:v1
  ```
* **Xóa Image không dùng**:
  ```bash
  docker rmi <IMAGE_ID_HOẶC_TÊN>
  ```

---

### 2.2. Quản lý Container (Chạy & Debug)
* **Xem container đang chạy**:
  ```bash
  docker ps
  ```
* **Xem tất cả container (kể cả đã tắt/bị lỗi)**:
  ```bash
  docker ps -a
  ```
* **Chạy container đơn lẻ**:
  ```bash
  docker run -d --name <TÊN_CONTAINER> -p <CỔNG_MÁY_THẬT>:<CỔNG_CONTAINER> <TÊN_IMAGE>
  ```
* **Chạy container cấp quyền GPU NVIDIA**:
  ```bash
  docker run -d --gpus all --name ml-gpu -p 8001:8001 ml-service:v1
  ```
* **Xem log thời gian thực để bắt lỗi (Cực kỳ quan trọng)**:
  ```bash
  docker logs -f <TÊN_CONTAINER>
  ```
* **Chui vào bên trong container để kiểm tra file / test mạng**:
  ```bash
  docker exec -it <TÊN_CONTAINER> sh
  # hoặc
  docker exec -it <TÊN_CONTAINER> bash
  ```
* **Dừng / Khởi động lại / Xóa container**:
  ```bash
  docker stop <TÊN_CONTAINER>
  docker restart <TÊN_CONTAINER>
  docker rm -f <TÊN_CONTAINER>
  ```

---

### 2.3. Quản lý Microservices với Docker Compose
```bash
# Khởi chạy toàn bộ hệ thống ngầm:
docker compose -f docker-compose.prod.yml up -d

# Tự động build lại và chạy:
docker compose -f docker-compose.prod.yml up -d --build

# Xem trạng thái các microservices:
docker compose -f docker-compose.prod.yml ps

# Xem log của 1 service cụ thể:
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f qwen-embedding

# Dừng và tắt toàn bộ hệ thống:
docker compose -f docker-compose.prod.yml down
```

---

### 2.4. Dọn dẹp giải phóng ổ cứng Docker
Khi ổ cứng bị đầy sau nhiều lần build:
```bash
docker system prune -a --volumes -f
```

---

## 3. CẨM NANG LỆNH GOOGLE CLOUD CLI (GCLOUD)

### 3.1. Cấu hình & Đăng nhập
```bash
# Đăng nhập tài khoản Google Cloud:
gcloud auth login

# Chọn Project làm việc:
gcloud config set project vinai-infrastructure-505416

# Kiểm tra Project hiện tại:
gcloud config get-value project
```

---

### 3.2. Google Artifact Registry (Kho lưu trữ Docker Image)
```bash
# 1. Bật dịch vụ Artifact Registry:
gcloud services enable artifactregistry.googleapis.com

# 2. Tạo kho lưu trữ Docker Image mới (tại Singapore):
gcloud artifacts repositories create scenesearch-repo \
    --repository-format=docker \
    --location=asia-southeast1 \
    --description="Docker images for SceneSearch"

# 3. Cấp quyền cho Docker trên máy tính kết nối vào kho GCP:
gcloud auth configure-docker asia-southeast1-docker.pkg.dev --quiet

# 4. Xem danh sách các Image đã push lên kho:
gcloud artifacts docker images list asia-southeast1-docker.pkg.dev/vinai-infrastructure-505416/scenesearch-repo
```

---

### 3.3. Google Compute Engine (Máy ảo VM & GPU)
```bash
# 1. Tạo máy ảo kèm GPU Tesla T4 (Dạng Spot tiết kiệm ~70% chi phí):
gcloud compute instances create scenesearch-t4 \
    --zone=asia-southeast1-b \
    --machine-type=n1-standard-4 \
    --accelerator=type=nvidia-tesla-t4,count=1 \
    --maintenance-policy=TERMINATE \
    --provisioning-model=SPOT \
    --instance-termination-action=STOP \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=100GB \
    --boot-disk-type=pd-balanced \
    --tags=http-server,https-server

# 2. Xem danh sách máy ảo và địa chỉ IP:
gcloud compute instances list

# 3. SSH vào máy ảo bằng 1 lệnh:
gcloud compute ssh scenesearch-t4 --zone=asia-southeast1-b

# 4. Mở Firewall cho cổng web (80, 443, 8088):
gcloud compute firewall-rules create allow-scenesearch \
    --allow=tcp:80,tcp:443,tcp:8088 \
    --target-tags=http-server,https-server

# 5. TẮT MÁY ẢO KHI KHÔNG DÙNG ĐỂ TIẾT KIỆM TIỀN:
gcloud compute instances stop scenesearch-t4 --zone=asia-southeast1-b

# 6. BẬT LẠI MÁY ẢO KHI LÀM VIỆC:
gcloud compute instances start scenesearch-t4 --zone=asia-southeast1-b
```

---

### 3.4. Google Cloud Run (Serverless Web)
```bash
# Deploy dịch vụ lên Cloud Run:
gcloud run deploy frontend-service \
    --image=asia-southeast1-docker.pkg.dev/vinai-infrastructure-505416/scenesearch-repo/frontend-service:v2 \
    --region=asia-southeast1 \
    --port=80 \
    --allow-unauthenticated

# Xem danh sách các dịch vụ Cloud Run:
gcloud run services list

# Xem log trực tiếp của Cloud Run:
gcloud run services logs tail frontend-service --region=asia-southeast1
```

---

### 3.5. Google Cloud Storage (Kho lưu trữ S3)
```bash
# Tạo Bucket lưu video gốc và sản phẩm phái sinh:
gcloud storage buckets create gs://scenesearch-raw-vinai --location=asia-southeast1
gcloud storage buckets create gs://scenesearch-derived-vinai --location=asia-southeast1

# Liệt kê các file trong Bucket:
gcloud storage ls gs://scenesearch-derived-vinai
```

---

## 4. QUY TRÌNH ĐÓNG GÓI & ĐẨY LÊN GCP ARTIFACT REGISTRY

Khi bạn thay đổi mã nguồn và muốn cập nhật các Image lên GCP:

```bash
#!/bin/bash
set -e

export PROJECT_ID="vinai-infrastructure-505416"
export REGION="asia-southeast1"
export REPO_NAME="scenesearch-repo"
export REGISTRY_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"

# Đăng nhập Docker vào Artifact Registry
gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin https://${REGION}-docker.pkg.dev

# 1. Frontend Service (Nginx + React)
docker build -f ./frontend/Dockerfile.prod -t ${REGISTRY_URL}/frontend-service:v2 -t ${REGISTRY_URL}/frontend-service:latest ./frontend
docker push ${REGISTRY_URL}/frontend-service:v2
docker push ${REGISTRY_URL}/frontend-service:latest

# 2. API Service (FastAPI)
docker build --build-arg EXTRAS=media -t ${REGISTRY_URL}/api-service:v1 -t ${REGISTRY_URL}/api-service:latest ./app
docker push ${REGISTRY_URL}/api-service:v1
docker push ${REGISTRY_URL}/api-service:latest

# 3. Worker Service (Celery Ingestion)
docker tag ${REGISTRY_URL}/api-service:v1 ${REGISTRY_URL}/worker-service:v1
docker tag ${REGISTRY_URL}/api-service:latest ${REGISTRY_URL}/worker-service:latest
docker push ${REGISTRY_URL}/worker-service:v1
docker push ${REGISTRY_URL}/worker-service:latest

# 4. ML Service (GPU - Qwen + SigLIP)
docker build --build-arg EXTRAS=ml -t ${REGISTRY_URL}/ml-service:v1 -t ${REGISTRY_URL}/ml-service:latest ./app
docker push ${REGISTRY_URL}/ml-service:v1
docker push ${REGISTRY_URL}/ml-service:latest

echo "🎉 Toàn bộ 4 Microservices đã được cập nhật lên GCP Artifact Registry!"
```

---

## 5. HAI PHƯƠNG ÁN TRIỂN KHAI HỆ THỐNG (DEPLOY)

### Phương án A: Máy ảo GPU (GCE VM) + Docker Compose (Khuyên dùng)
> **Ưu điểm**: Triển khai nhanh trong 5 phút, 1 VM quản lý toàn bộ stack, GPU T4 ổn định, chi phí rẻ (~$35/tháng với Spot VM).

1. **SSH vào VM**:
   ```bash
   gcloud compute ssh scenesearch-t4 --zone=asia-southeast1-b
   ```
2. **Cài đặt NVIDIA Container Toolkit (1 lần duy nhất)**:
   ```bash
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
     sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
     sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
   ```
3. **Tạo thư mục & file cấu hình `.env`**:
   ```bash
   mkdir -p ~/scenesearch && cd ~/scenesearch
   ```
   Tạo file `.env`:
   ```ini
   APP_NAME=SceneSearch-P-081
   APP_ENV=production
   APP_DEBUG=false
   APP_HOST=0.0.0.0
   APP_PORT=8000
   APP_CORS_ORIGINS=["*"]

   POSTGRES_USER=scenesearch
   POSTGRES_PASSWORD=scenesearch_secure_password
   POSTGRES_DB=scenesearch
   DATABASE_URL=postgresql+asyncpg://scenesearch:scenesearch_secure_password@postgres:5432/scenesearch

   REDIS_URL=redis://redis:6379/0
   CELERY_BROKER_URL=redis://redis:6379/1
   CELERY_RESULT_BACKEND=redis://redis:6379/2

   # Google Cloud Storage (Thay thế MinIO)
   MINIO_ENDPOINT=storage.googleapis.com
   MINIO_SECURE=true
   MINIO_ACCESS_KEY=<GCS_HMAC_ACCESS_KEY>
   MINIO_SECRET_KEY=<GCS_HMAC_SECRET_KEY>
   MINIO_RAW_BUCKET=scenesearch-raw-vinai
   MINIO_DERIVED_BUCKET=scenesearch-derived-vinai
   MINIO_SCENE_MEDIA_ENDPOINT=storage.googleapis.com
   MINIO_SCENE_MEDIA_BUCKET=scenesearch-derived-vinai
   MINIO_SCENE_MEDIA_SECURE=true
   MINIO_SCENE_MEDIA_CONSOLE=false

   # Qdrant Vector DB
   QDRANT_URL=https://qdrant.viettech.fit:443
   QDRANT_COLLECTION=Scences
   QDRANT_VECTOR_SIZE=2048
   QDRANT_API_KEY=ai20k_tHMKPd49T1_ggY2lQDXcnGEklENw_lnb

   # ML Inference
   SEARCH_MODE=qwen
   SEARCH_VISUAL_VECTOR=qwen
   ML_ENCODER_NAME=Qwen/Qwen3-VL-Embedding-2B
   ML_QWEN_MODEL_NAME=Qwen/Qwen3-VL-Embedding-2B
   ML_MODEL_VERSION=qwen3-vl-embedding-2b-v1
   QWEN_EMBEDDING_URL=http://qwen-embedding:8001
   QWEN_EMBEDDING_API_KEY=scenesearch-internal

   # Agentic Search
   SEARCH_AGENTIC_ENABLED=true
   SEARCH_HYDE_ENABLED=true
   SEARCH_DOMAIN_GUARDRAIL_ENABLED=true
   LLM_BASE_URL=https://integrate.api.nvidia.com/v1
   LLM_API_KEY=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
   LLM_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning
   ```
4. **Tạo file `docker-compose.prod.yml`**:
   ```yaml
   name: scenesearch-prod

   services:
     qwen-embedding:
       image: asia-southeast1-docker.pkg.dev/vinai-infrastructure-505416/scenesearch-repo/ml-service:v1
       command: uvicorn ml.embedding_api:app --host 0.0.0.0 --port 8001 --workers 1
       env_file: .env
       environment:
         ML_DEVICE: cuda
         ML_DTYPE: float16
       deploy:
         resources:
           reservations:
             devices:
               - {driver: nvidia, count: 1, capabilities: [gpu]}
       expose: ["8001"]
       volumes:
         - huggingface_cache:/home/appuser/.cache/huggingface
       restart: unless-stopped

     api:
       image: asia-southeast1-docker.pkg.dev/vinai-infrastructure-505416/scenesearch-repo/api-service:v1
       command: sh -c "alembic upgrade head && exec uvicorn api.main:app --host 0.0.0.0 --port 8000"
       env_file: .env
       expose: ["8000"]
       depends_on: [qwen-embedding, postgres, redis]
       restart: unless-stopped

     worker:
       image: asia-southeast1-docker.pkg.dev/vinai-infrastructure-505416/scenesearch-repo/worker-service:v1
       command: celery -A worker.celery_app:celery_app worker -Q ingestion --loglevel=INFO --pool=solo
       env_file: .env
       depends_on: [qwen-embedding, redis, postgres]
       restart: unless-stopped

     frontend:
       image: asia-southeast1-docker.pkg.dev/vinai-infrastructure-505416/scenesearch-repo/frontend-service:v2
       ports: ["80:80"]
       depends_on: [api]
       restart: unless-stopped

     postgres:
       image: postgres:16-alpine
       env_file: .env
       volumes: [postgres_data:/var/lib/postgresql/data]
       restart: unless-stopped

     redis:
       image: redis:7-alpine
       restart: unless-stopped

   volumes:
     postgres_data:
     huggingface_cache:
   ```
5. **Kéo Image & Chạy**:
   ```bash
   gcloud auth configure-docker asia-southeast1-docker.pkg.dev --quiet
   docker compose -f docker-compose.prod.yml pull
   docker compose -f docker-compose.prod.yml up -d
   ```

---

### Phương án B: Serverless (Cloud Run + GCS + Qdrant Cloud)
> **Ưu điểm**: Tự tắt về 0 khi không có người dùng, miễn phí chứng chỉ HTTPS, tự scale.

1. **Deploy Frontend**:
   ```bash
   gcloud run deploy frontend-service \
       --image=asia-southeast1-docker.pkg.dev/vinai-infrastructure-505416/scenesearch-repo/frontend-service:v2 \
       --region=asia-southeast1 \
       --port=80 \
       --allow-unauthenticated
   ```
2. **Deploy API Gateway**:
   ```bash
   gcloud run deploy api-service \
       --image=asia-southeast1-docker.pkg.dev/vinai-infrastructure-505416/scenesearch-repo/api-service:v1 \
       --region=asia-southeast1 \
       --port=8000 \
       --memory=2Gi \
       --cpu=2 \
       --env-vars-file=./app/env.yaml \
       --allow-unauthenticated
   ```

---

## 6. BẢNG TRA CỨU LỖI THƯỜNG GẶP & CÁCH KHẮC PHỤC (TROUBLESHOOTING)

### 🔴 Lỗi 1: Cloud Run báo `STARTUP TCP probe failed ... on port 80/8080`
* **Nguyên nhân**: Nginx bị crash ngay lúc bật do `proxy_pass http://api:8000` không tìm thấy DNS của chữ `api`.
* **Cách khắc phục**:
  * Thêm `resolver 8.8.8.8 1.1.1.1 valid=30s ipv6=off;` vào `frontend/nginx.conf`.
  * Đổi sang dùng biến runtime: `set $backend "${API_PROXY_TARGET:-http://api:8000}"; proxy_pass $backend$request_uri;`.

### 🔴 Lỗi 2: `ZONE_RESOURCE_POOL_EXHAUSTED` khi tạo VM GPU
* **Nguyên nhân**: Data center tại Zone bạn chọn tạm thời hết card GPU vật lý.
* **Cách khắc phục**:
  * Đổi zone sang `asia-southeast1-a`, `asia-southeast1-c`, `asia-east1-a` (Đài Loan), hoặc `us-central1-a` (Mỹ).
  * Chuyển từ card T4 sang card thế hệ mới **NVIDIA L4** (`g2-standard-4`).

### 🔴 Lỗi 3: `docker-credential-gcloud: executable file not found in $PATH`
* **Nguyên nhân**: Docker trên WSL2 không gọi được binary credential helper của Windows.
* **Cách khắc phục**: Đăng nhập trực tiếp bằng Access Token:
  ```bash
  gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin https://asia-southeast1-docker.pkg.dev
  ```

### 🔴 Lỗi 4: Video / Thumbnail từ MinIO hoặc Storage không hiển thị (HTTP 401)
* **Nguyên nhân**: Thẻ `<video>` và `<img>` không tự gửi header Authorization, backend bắt buộc phải đọc từ Cookie `scenesearch_jwt`.
* **Cách khắc phục**: Người dùng phải đăng nhập trên web để trình duyệt lưu Cookie `scenesearch_jwt`. Đồng thời đảm bảo bucket `scenesearch-derived` có chứa các file thumbnail `.jpg` và clip `.mp4`.

### 🔴 Lỗi 5: Tìm kiếm (Search) báo lỗi 503 hoặc trả về 0 kết quả
* **Nguyên nhân**:
  1. `qwen-embedding` chưa khởi động xong hoặc chưa load model vào GPU.
  2. Qdrant URL hoặc API Key cấu hình sai.
  3. Query bị LLM Guardrail đánh giá là Out-of-Domain (không thuộc cảnh đường phố/giao thông).
* **Cách khắc phục**: Kiểm tra log container `docker logs -f qwen-embedding` và kiểm tra biến `QWEN_EMBEDDING_URL` trong `.env`.
