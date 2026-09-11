# SceneSearch (P-081) — System Architecture Diagram & Component Specifications

> 🌐 **Official Live Domain:** [https://c3-app-081.vinai.io.vn/](https://c3-app-081.vinai.io.vn/) *(Cloud Run: [https://scenesearch-604840409374.asia-southeast1.run.app](https://scenesearch-604840409374.asia-southeast1.run.app))*  
> 🎥 **Video Demo (5 Mins):** [https://drive.google.com/file/d/1gXYMA_KUQKXAMoWqEM4tfmlxS2FZBpq8/view?usp=sharing](https://drive.google.com/file/d/1gXYMA_KUQKXAMoWqEM4tfmlxS2FZBpq8/view?usp=sharing)  
> 📊 **Pitch Deck Slides:** [https://drive.google.com/file/d/12VwYiEgA-HEAYQIE1Vo7gIWLeQOJIMpq/view?usp=sharing](https://drive.google.com/file/d/12VwYiEgA-HEAYQIE1Vo7gIWLeQOJIMpq/view?usp=sharing)  

This document outlines the complete architectural design, data pipelines, multi-container microservice topology, and infrastructure components of **SceneSearch (P-081)** — an intelligent multimodal driving-scene search and video indexing platform.

---

## 1. High-Level System Architecture Diagram

```mermaid
flowchart TD
    %% CLIENT & INGRESS
    subgraph CLIENT_LAYER ["🌐 CLIENT & INGRESS LAYER"]
        User["👤 End User / Autonomous AI Engineer"]
        Browser["🖥️ React 19 SPA (Vite + Tailwind CSS)"]
        Nginx["🛡️ Nginx Reverse Proxy (Port 80)"]
        
        User -->|"HTTPS / Web Browser"| Browser
        Browser -->|"Same-Origin /api/* Requests"| Nginx
    end

    %% MULTI-CONTAINER CLOUD RUN POD
    subgraph CLOUD_RUN_POD ["☁️ GOOGLE CLOUD RUN POD / DOCKER COMPOSE NETWORK"]
        Nginx -->|"Proxy Pass 127.0.0.1:8000"| FastAPI["⚡ Backend API Service (FastAPI)"]
        
        subgraph BACKEND_SERVICES ["Internal Microservices & Daemons"]
            FastAPI -->|"Agentic Parser & Search Engine"| Engine["🔍 SceneSearchEngine"]
            FastAPI -->|"Enqueue Video Job"| Celery["⚙️ Ingestion Worker (Celery Daemon)"]
            FastAPI -->|"Vector Embedding HTTP :8001"| EmbeddingAPI["🧠 Qwen3-VL & SigLIP Embedding Service"]
            Celery -->|"Frame Encoding :8001"| EmbeddingAPI
            
            Engine -->|"APM Span Traces"| Tracer["⏱️ SystemTraceRecorder (In-Memory APM)"]
            Engine -->|"Tri-Tier Agentic Reasoning"| Agent["🤖 Agentic Orchestrator (Visual-HyDE + Reflection)"]
        end
    end

    %% EXTERNAL MANAGED INFRASTRUCTURE
    subgraph MANAGED_INFRASTRUCTURE ["🏢 BACKING INFRASTRUCTURE & MANAGED SERVICES"]
        Postgres[("🐘 Google Cloud SQL<br/>(PostgreSQL 16)")]
        Redis[("⚡ Upstash Redis Serverless<br/>(Cache & Celery Broker)")]
        Qdrant[("🎯 Qdrant Cloud Cluster<br/>(Collection 'Scences' 2048d)")]
        MinIO[("🪣 Google Cloud Storage / MinIO S3<br/>('scenesearch-raw' & 'scencesearch-frames')")]
        NvidiaLLM["✨ NVIDIA NIM LLM<br/>(moonshotai/kimi-k3)"]
        
        FastAPI -->|"JWT Auth, Users, Datasets"| Postgres
        FastAPI -->|"Status Cache & RLHF Sync"| Redis
        Celery -->|"Fetch Tasks & Store State"| Redis
        Celery -->|"Store Raw Video & Anonymized Frames"| MinIO
        Celery -->|"Upsert Scene Vectors"| Qdrant
        
        Agent -->|"Single-Pass Guardrail & HyDE"| NvidiaLLM
        Engine -->|"Hybrid Vector Similarity Search"| Qdrant
        FastAPI -->|"Stream Video & Thumbnails"| MinIO
    end

    %% STYLING
    classDef client fill:#f9f5eb,stroke:#000,stroke-width:2px;
    classDef compute fill:#e6f4ea,stroke:#137333,stroke-width:2px;
    classDef infra fill:#fef7e0,stroke:#b06000,stroke-width:2px;
    classDef ai fill:#f3e8fd,stroke:#7627bb,stroke-width:2px;
    
    class User,Browser,Nginx client;
    class FastAPI,Engine,Celery,Tracer compute;
    class Postgres,Redis,Qdrant,MinIO infra;
    class EmbeddingAPI,Agent,NvidiaLLM ai;
```

---

## 2. Ingestion & Video Processing Pipeline

```mermaid
sequenceDiagram
    autonumber
    actor Admin as 👤 Admin / Ingest Pipeline
    participant API as ⚡ FastAPI (/api/v1/ingest)
    participant S3 as 🪣 MinIO S3 Storage
    participant Celery as ⚙️ Celery Ingestion Worker
    participant Anon as 🎭 Anonymizer (YOLO Face & Plate)
    participant Embed as 🧠 Qwen3-VL Embedding API
    participant Qdrant as 🎯 Qdrant Vector Database
    participant DB as 🐘 PostgreSQL Database

    Admin->>API: Upload raw MP4 video clip
    API->>S3: Save to 'scenesearch-raw' bucket
    API->>DB: Create video corpus record (status: PENDING)
    API->>Celery: Enqueue ingestion task (Q: ingestion)
    
    Celery->>S3: Stream raw MP4 video
    Celery->>Celery: Sample keyframes (SSIM + 0.5s temporal window)
    
    loop For each extracted keyframe
        Celery->>Anon: Detect & Gaussian-blur faces & license plates
        Celery->>S3: Store sanitized derivative in 'scencesearch-frames'
        Celery->>Embed: POST /embeddings (image tensor)
        Embed-->>Celery: Return 2048-dim normalized dense vector
        Celery->>Qdrant: Upsert point (vector + metadata payload)
    end
    
    Celery->>DB: Update corpus record (status: COMPLETED)
    Celery-->>API: Task complete notification
```

---

## 3. Tri-Tier Agentic Search Pipeline

```mermaid
flowchart TD
    Query["📝 User Query: 'Xe tải rẽ trái trời mưa không có người đi bộ'"]
    
    subgraph TIER_1 ["TIER 1: DOMAIN GUARDRAIL & QUERY PARSER"]
        Query --> Guardrail{"Domain Check"}
        Guardrail -->|"Out-of-Domain (e.g. nấu ăn, lập trình)"| Reject["🚫 Trả về 0 kết quả hợp lý kèm giải thích"]
        Guardrail -->|"In-Domain Driving Scene"| HyDE["✨ Visual-HyDE Expansion (NVIDIA NIM)"]
    end
    
    subgraph TIER_2 ["TIER 2: MULTIMODAL DENSE RETRIEVAL"]
        HyDE -->|"Sinh câu mô tả thị giác chi tiết (POV dashcam)"| ModelServer["🧠 Qwen3-VL Embedding API (:8001)"]
        ModelServer -->|"Query Vector (2048d)"| QdrantSearch["🎯 Qdrant Vector Search (Cosine Similarity)"]
        QdrantSearch -->|"Top-50 candidates"| Filtering["🔍 Filter: Metadata, Time of Day, Weather, Floor >= 0.09"]
    end
    
    subgraph TIER_3 ["TIER 3: REFLECTION & CORRECTION LOOP"]
        Filtering --> CheckZero{"Kết quả rỗng do điều kiện loại trừ quá khắt khe?"}
        CheckZero -->|"Có & còn vòng lặp"| Relax["🔄 Adaptive Relaxation: Nới lỏng thuộc tính phụ"]
        Relax --> ModelServer
        CheckZero -->|"Đã tối ưu / Có kết quả"| FinalResults["📦 Trả về Top Video Scenes & Timestamps chính xác"]
    end
```

---

## 4. Component Technical Specifications

| Component | Technology | Role & Responsibility | Resource Limits |
| :--- | :--- | :--- | :--- |
| **Frontend Web UI** | React 19, Vite, Tailwind CSS, Lucide | Giao diện tìm kiếm brutalist đa ngôn ngữ, trình phát video theo dõi timeline, trung tâm trích xuất dataset, APM trace explorer. | Nginx Ingress: 1 CPU, 1GB RAM |
| **Backend API Gateway** | FastAPI, Python 3.11, Pydantic v2, SQLAlchemy 2 | Quản lý định tuyến RESTful, xác thực JWT, điều phối Agentic Search, APM tracing, tích hợp Cloud SQL & Upstash. | 2 CPU, 6GB RAM |
| **Multimodal Embedding Service** | PyTorch, HuggingFace Transformers, Sentence-Transformers | Microservice chuyên dụng lưu trữ và thực thi mô hình `Qwen/Qwen3-VL-Embedding-2B` và `ViT-B-16-SigLIP`. | 4 CPU, 16GB RAM (hoặc GPU Tesla T4) |
| **Background Ingestion Worker** | Celery, FFmpeg, OpenCV, Ultralytics YOLO | Xử lý video bất đồng bộ, trích xuất khung hình thông minh SSIM, làm mờ mặt và biển số xe bảo vệ quyền riêng tư. | 1 CPU, 2GB RAM |
| **Relational Database** | PostgreSQL 16 (Google Cloud SQL) | Lưu trữ người dùng, phân quyền RBAC, metadata video, tập dữ liệu đánh giá, log phản hồi RLHF. | Google Cloud SQL Managed |
| **Vector Database** | Qdrant Cloud Cluster | Lưu trữ và tìm kiếm vector 2048 chiều (Qwen) và 768 chiều (SigLIP) với bộ lọc payload đa thuộc tính HNSW. | Viettech Cloud Cluster |
| **Object Storage** | MinIO / Google Cloud Storage | Phân tách bảo mật giữa video gốc (`scenesearch-raw`) và khung hình phái sinh đã ẩn danh (`scencesearch-frames`). | GCS S3-compatible |
| **Cache & Task Queue** | Redis (Upstash Serverless) | Lưu trạng thái tác vụ Celery, blacklisted JWT tokens, cache kết quả tìm kiếm nóng. | Upstash Redis TLS |
| **LLM Reasoning Agent** | NVIDIA NIM API (`moonshotai/kimi-k3`) | Phân loại OOD guardrail, sinh mô tả thị giác Visual-HyDE, trích xuất concept ràng buộc. | Serverless HTTPS |

---

## 5. Security & Privacy Architecture (ADR-0003)

- **Two-Bucket Isolation**: Video gốc chứa thông tin nhận dạng cá nhân (PII) được lưu riêng biệt trong bucket bảo mật `scenesearch-raw` (chỉ worker nội bộ truy cập). Khung hình hiển thị cho người dùng lưu trong `scencesearch-frames` và bắt buộc phải qua bước làm mờ tự động.
- **Stateless In-Memory APM Tracing**: Không ghi log thông tin nhạy cảm vào ổ đĩa; trace được lưu trữ trên ring buffer bộ nhớ RAM với cơ chế tự động xoay vòng 100 bản ghi gần nhất.
- **JWT Authentication & RBAC**: Phân quyền nghiêm ngặt 3 cấp độ: `admin` (toàn quyền upload, eval, telemetry), `engineer` (tìm kiếm, tạo draft, xuất dataset), và `annotator` (gắn nhãn RLHF).
