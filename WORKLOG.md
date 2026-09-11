# 📋 SceneSearch (P-081) — Daily Engineering Worklog

> 🌐 **Official Live Domain:** [https://c3-app-081.vinai.io.vn/](https://c3-app-081.vinai.io.vn/) *(Cloud Run: [https://scenesearch-604840409374.asia-southeast1.run.app](https://scenesearch-604840409374.asia-southeast1.run.app))*  
> 🎥 **Video Demo (5 Mins):** [https://drive.google.com/file/d/1gXYMA_KUQKXAMoWqEM4tfmlxS2FZBpq8/view?usp=sharing](https://drive.google.com/file/d/1gXYMA_KUQKXAMoWqEM4tfmlxS2FZBpq8/view?usp=sharing)  
> 📊 **Pitch Deck Slides:** [https://drive.google.com/file/d/12VwYiEgA-HEAYQIE1Vo7gIWLeQOJIMpq/view?usp=sharing](https://drive.google.com/file/d/12VwYiEgA-HEAYQIE1Vo7gIWLeQOJIMpq/view?usp=sharing)  

This worklog records the daily activity, member contributions, features implemented, bug fixes, and milestones achieved during the development of **SceneSearch (P-081)**.

---

## 🗓️ Phase 1: Foundation & Data Pipelines

### Day 1: Project Setup & Specification
- **Thành viên:** Backend Team & Architect
- **Công việc thực hiện:**
  - Khởi tạo cấu trúc repository theo chuẩn Monorepo (`app/`, `frontend/`, `docs/`, `scripts/`).
  - Soạn thảo tài liệu đặc tả kỹ thuật [`docs/SRS.md`](docs/SRS.md) và [`docs/MVP.md`](docs/MVP.md).
  - Viết các quyết định kiến trúc cốt lõi: ADR-0001 (Encoder & Vector size), ADR-0002 (Corpus & Granularity), ADR-0003 (Anonymization Policy).
- **Kết quả:** Setup hoàn tất môi trường phát triển, Docker Compose nền tảng và tài liệu kiến trúc.

### Day 2: Relational Schema & Storage Setup
- **Thành viên:** Backend Team
- **Công việc thực hiện:**
  - Thiết kế database models trên PostgreSQL với SQLAlchemy 2: `User`, `VideoCorpus`, `TaskStatusRecord`, `RLHFFeedback`.
  - Cấu hình Alembic migrations cho PostgreSQL.
  - Tích hợp MinIO SDK kết nối với Google Cloud Storage buckets: `scenesearch-raw-vinai` và `scencesearch-frames-vinai`.
- **Kết quả:** Các migration được áp dụng thành công; storage client kiểm tra kết nối 3 bucket tự động khi khởi động.

### Day 3: Video Ingestion & Anonymization Pipeline
- **Thành viên:** ML & Worker Team
- **Công việc thực hiện:**
  - Xây dựng Celery Ingestion Worker (`app/worker/tasks/ingest.py`).
  - Tích hợp FFmpeg trích xuất khung hình ở tần suất 2 FPS (0.5s / frame) kết hợp bộ lọc SSIM để bỏ qua frame tĩnh.
  - Tích hợp mô hình YOLOv8 phát hiện khuôn mặt và biển số xe, áp dụng thuật toán Gaussian Blur tự động.
- **Kết quả:** Video upload được tự động phân tách thành các khung hình an toàn, sẵn sàng cho việc embedding.

---

## 🗓️ Phase 2: Multimodal Embedding & Search Engine

### Day 4: Qwen3-VL & SigLIP Model Service
- **Thành viên:** ML Team
- **Công việc thực hiện:**
  - Xây dựng microservice độc lập `embedding-api` (`app/ml/embedding_api.py`) hosting mô hình `Qwen/Qwen3-VL-Embedding-2B` và `ViT-B-16-SigLIP`.
  - Xây dựng các endpoints: `GET /health`, `POST /embeddings`, `GET /model/status`, `POST /model/load`.
  - Cấu hình hỗ trợ inference linh hoạt trên cả GPU (CUDA float16) và CPU (bfloat16 / float32).
- **Kết quả:** Service embedding độc lập với thời gian trích xuất vector < 50ms cho câu truy vấn văn bản.

### Day 5: Vector Indexing & Qdrant Cloud Integration
- **Thành viên:** Backend Team
- **Công việc thực hiện:**
  - Kết nối Qdrant Cloud cluster (`https://qdrant.viettech.fit:443`).
  - Khởi tạo collection `Scences` hỗ trợ multi-vector schema (vector `qwen` 2048d và vector `siglip` 768d).
  - Thiết lập chỉ mục HNSW payload cho các trường metadata: `weather`, `time_of_day`, `scene_type`, `car_count`.
- **Kết quả:** Đã nạp và lập chỉ mục hơn 29,504+ khung hình từ tập dữ liệu BDD-100K 20GB.

### Day 6: Tri-Tier Agentic Search & HyDE
- **Thành viên:** AI & Backend Team
- **Công việc thực hiện:**
  - Xây dựng `TriTierAgentOrchestrator` (`app/search/agent.py`) kết nối với NVIDIA NIM LLM (`moonshotai/kimi-k3`).
  - Triển khai **Tier 1**: Domain Guardrail phân loại và từ chối thông minh các truy vấn ngoài ngành (OOD).
  - Triển khai **Tier 2**: Visual-HyDE sinh mô tả chi tiết góc nhìn camera hành trình để mở rộng câu truy vấn ngắn.
  - Triển khai **Tier 3**: Reflection Loop tự động nới lỏng các điều kiện loại trừ khắt khe khi kết quả rỗng.
- **Kết quả:** Cải thiện tỷ lệ tìm kiếm chính xác cho câu truy vấn tiếng Việt ngắn từ 45% lên 89.77% Hit@5.

---

## 🗓️ Phase 3: Frontend Web UI & Dataset Slicing

### Day 7: Neo-Brutalism UI & Search Experience
- **Thành viên:** Frontend Team
- **Công việc thực hiện:**
  - Xây dựng giao diện tìm kiếm `SearchPage.jsx` trên nền tảng React 19 + Tailwind CSS phong cách Neo-Brutalist.
  - Tạo thanh tìm kiếm thông minh với phím tắt nhanh (`/`), gợi ý từ khóa thông minh, và bảng bộ lọc thuộc tính.
  - Phát triển component `SceneCard.jsx` hiển thị thumbnail, độ tương đồng (similarity score), tags và nhãn metadata.
- **Kết quả:** Giao diện tốc độ cao, responsive trên cả desktop và mobile.

### Day 8: Video Player with Range Seeking & Dataset Slicer
- **Thành viên:** Frontend Team
- **Công việc thực hiện:**
  - Xây dựng modal xem video tương tác hỗ trợ tua chính xác đến từng giây chứa sự kiện phát hiện.
  - Cấu hình Nginx reverse proxy hỗ trợ HTTP 206 Partial Content (Byte-Range requests).
  - Xây dựng khay gom dữ liệu (`SelectionTray.jsx`) và trang quản lý bản nháp (`DatasetDraftPage.jsx`).
  - Tích hợp tính năng xuất khẩu dataset dạng tệp `JSONL` và gói tệp `ZIP` hình ảnh đã ẩn danh.
- **Kết quả:** Cho phép kỹ sư AI chọn lọc và tải về các lát cắt dữ liệu (dataset slices) phục vụ huấn luyện mô hình.

### Day 9: RLHF In-Loop Feedback System
- **Thành viên:** Fullstack Team
- **Công việc thực hiện:**
  - Tích hợp nút đánh giá liên quan (👍 / 👎) trực tiếp trên từng thẻ video kết quả tìm kiếm.
  - Xây dựng API `/api/v1/feedback` và bảng lưu trữ `RLHFFeedback` trong PostgreSQL.
  - Xây dựng trang quản trị phản hồi RLHF (`RLHFFeedbackTable.jsx`) trong Admin Console.
- **Kết quả:** Thu thập dữ liệu phản hồi thực tế từ người dùng để phục vụ huấn luyện Reward Model.

---

## 🗓️ Phase 4: Evaluation, In-App Tracing & Production Deployment

### Day 10: Golden Dataset & Benchmark Harness
- **Thành viên:** ML & QA Team
- **Công việc thực hiện:**
  - Biên soạn tập dữ liệu chuẩn Ground-Truth [`app/eval/golden_set/eval.csv`](app/eval/golden_set/eval.csv) gồm 88 cặp truy vấn - khung hình.
  - Xây dựng bộ đo kiểm tự động `app/eval/` tính toán HitRate@K (K=1, 3, 5, 10, 20, 50) và MRR cho 3 cấp độ: Video-Level, Frame-Tolerant (±4f) và Frame-Exact.
  - Thực hiện nghiên cứu bóc tách (Ablation Study) mô hình Cross-Encoder Reranker (`Qwen3-VL-Reranker-2B`).
- **Kết quả:** Qwen3-VL 2B đạt 89.77% Hit@5 và 0.8016 MRR; tài liệu hóa toàn bộ kết quả trong [`eval/results/report.md`](eval/results/report.md).

### Day 11: In-App APM Trace Explorer
- **Thành viên:** Backend & Frontend Team
- **Công việc thực hiện:**
  - Xây dựng `SystemTraceRecorder` (`app/core/tracer.py`) sử dụng cấu trúc dữ liệu Ring Buffer trên bộ nhớ RAM.
  - Đo đạc chi tiết từng micro-span: `parser`, `llm`, `embedding`, `vectordb`, `rerank`, `cache`.
  - Xây dựng giao diện `TraceExplorer.jsx` với biểu đồ Gantt Waterfall, live polling 3s và các KPI P50/P95.
- **Kết quả:** Giám sát thời gian thực toàn bộ chuỗi tìm kiếm với độ trễ thu thập < 0.1ms và zero disk I/O.

### Day 12: Admin Localization & Golden Set Integration
- **Thành viên:** Frontend Team
- **Công việc thực hiện:**
  - Bản địa hóa toàn bộ giao diện sang tiếng Việt tự nhiên và chuyên nghiệp.
  - Xây dựng component `EvaluationBenchmark.jsx` tích hợp trực tiếp bảng đánh giá Benchmark và mô tả Dataset BDD-100K / Golden Set vào Admin Control Center.
  - Bổ sung tab điều hướng "Đánh giá & Benchmark" vào Sidebar.
- **Kết quả:** Admin Console hoàn thiện và thống nhất trải nghiệm người dùng.

### Day 13: Full Build, Unit Test Verification & Cloud Run Multi-Container Deploy
- **Thành viên:** DevOps & Fullstack Team
- **Công việc thực hiện:**
  - Kiểm thử toàn diện: Chạy thành công **421 / 421 tests backend (100% PASS)** và **7 / 7 tests frontend**.
  - Đóng gói toàn bộ hệ thống qua Docker Compose (3 container images).
  - Tự động hóa pipeline Cloud Run Multi-Container (`scripts/deploy-multicontainer.sh`) và deploy thành công lên Google Cloud Run.
- **Kết quả:** Hệ thống live trên Cloud Run tại URL: **`https://scenesearch-604840409374.asia-southeast1.run.app`**.
