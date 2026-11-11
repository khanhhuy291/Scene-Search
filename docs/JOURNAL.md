# 📔 SceneSearch (P-081) — Weekly Engineering Journal

> 🌐 **Official Live Domain:** [https://c3-app-081.vinai.io.vn/](https://c3-app-081.vinai.io.vn/) *(Cloud Run: [https://scenesearch-604840409374.asia-southeast1.run.app](https://scenesearch-604840409374.asia-southeast1.run.app))*  
> 🎥 **Video Demo (5 Mins):** [https://drive.google.com/file/d/1gXYMA_KUQKXAMoWqEM4tfmlxS2FZBpq8/view?usp=sharing](https://drive.google.com/file/d/1gXYMA_KUQKXAMoWqEM4tfmlxS2FZBpq8/view?usp=sharing)  
> 📊 **Pitch Deck Slides:** [https://drive.google.com/file/d/12VwYiEgA-HEAYQIE1Vo7gIWLeQOJIMpq/view?usp=sharing](https://drive.google.com/file/d/12VwYiEgA-HEAYQIE1Vo7gIWLeQOJIMpq/view?usp=sharing)  

This engineering journal documents the chronological evolution, weekly goals, accomplishments, architectural hurdles, and key lessons learned throughout the development of **SceneSearch (P-081)**.

---

## 📅 Week 1: Problem Definition, Data Pipeline & Architecture Design

### 🎯 Mục tiêu Tuần (Weekly Objectives)
1. Khảo sát bài toán tìm kiếm video xe tự hành đa phương thức (Multimodal Autonomous Driving Scene Retrieval).
2. Thiết kế kiến trúc tổng thể hệ thống (System Architecture, SRS, MVP specification).
3. Xây dựng pipeline xử lý video: Video Ingestion, Sampling khung hình thông minh (SSIM) và quy chuẩn làm mờ mặt / biển số xe (ADR-0003).
4. Thiết lập môi trường Docker Compose và cơ sở dữ liệu PostgreSQL / MinIO / Redis.

### ✅ Kết quả Đã Hoàn Thành (Accomplishments)
- Hoàn thiện tài liệu kiến trúc kỹ thuật [`docs/SRS.md`](docs/SRS.md), [`docs/MVP.md`](docs/MVP.md), và các Architecture Decision Records ([`docs/adr/`](docs/adr/)).
- Xây dựng Celery Worker bất đồng bộ (`app/worker/`) tích hợp FFmpeg để giải mã video và trích xuất keyframes theo cửa sổ 0.5s.
- Tích hợp model YOLOv8 / OpenCV để nhận diện khuôn mặt, biển số xe và áp dụng Gaussian blur bảo vệ quyền riêng tư dữ liệu trước khi lưu vào bucket phái sinh.
- Hoàn thiện database schema trên PostgreSQL với SQLAlchemy 2 và Alembic migrations.

### ⚠️ Khó khăn & Thách thức (Challenges & Blockers)
- *Vấn đề:* Xử lý video dung lượng lớn (BDD-100K 20GB) trong container gặp hiện tượng nghẽn I/O và tràn RAM khi giải mã khung hình.
- *Giải pháp:* Tách kiến trúc thành 2 bucket độc lập: `scenesearch-raw` (chỉ lưu trữ video gốc) và `scencesearch-frames` (lưu trữ frame phái sinh nhẹ). Áp dụng thuật toán lọc SSIM để bỏ qua các frame trùng lặp khi xe dừng đèn đỏ.

### 💡 Bài học Kinh nghiệm (Key Lessons Learned)
- Việc phân tách rõ ràng giữa storage gốc và storage phái sinh (Two-Bucket Isolation) là nguyên tắc sống còn để đảm bảo tuân thủ GDPR và quyền riêng tư trong dữ liệu camera hành trình.

---

## 📅 Week 2: Multimodal Embedding Model & Vector Indexing

### 🎯 Mục tiêu Tuần (Weekly Objectives)
1. Thử nghiệm và tích hợp các mô hình Vision-Language (SigLIP ViT-B-16, Qwen3-VL-Embedding-2B).
2. Xây dựng Vector Search Index trên Qdrant với vector 2048 chiều và 768 chiều.
3. Tạo tập dữ liệu đánh giá chuẩn Ground-Truth (Golden Dataset 88 queries).
4. Phát triển Agentic Search Tri-Tier và cơ chế mở rộng ngữ nghĩa Visual-HyDE.

### ✅ Kết quả Đã Hoàn Thành (Accomplishments)
- Triển khai microservice độc lập `embedding-api` (`app/ml/embedding_api.py`) lưu trữ mô hình `Qwen/Qwen3-VL-Embedding-2B` trên GPU/CPU với chuẩn REST API `/embeddings`.
- Tích hợp Qdrant Cloud Cluster với collection `Scences`, hỗ trợ đa vector (named vectors) và bộ lọc thuộc tính HNSW (thời tiết, mật độ giao thông, số lượng xe, sự kiện).
- Xây dựng bộ đánh giá tự động `app/eval/` và file ground-truth `app/eval/golden_set/eval.csv` gồm 88 cặp câu truy vấn đa ngôn ngữ (VN & EN).
- Triển khai Tri-Tier Agentic Search:
  - **Tier 1:** Domain Guardrail lọc các câu truy vấn ngoài phạm vi (OOD) bằng regex + LLM classifier.
  - **Tier 2:** Sinh mô tả thị giác chi tiết góc nhìn camera hành trình (Visual-HyDE).
  - **Tier 3:** Vòng lặp phản tư (Reflection Loop) tự động nới lỏng điều kiện khi gặp zero-hit.

### ⚠️ Khó khăn & Thách thức (Challenges & Blockers)
- *Vấn đề:* Câu truy vấn ngắn bằng tiếng Việt (ví dụ: *"xe hơi trời mưa"*) có độ tương đồng cosine thấp với ảnh do model vision được train trên caption tiếng Anh chi tiết.
- *Giải pháp:* Sử dụng mô hình LLM thông qua NVIDIA NIM để mở rộng câu truy vấn ngắn thành mô tả thị giác chi tiết dạng góc nhìn kính lái trước khi đưa vào encoder (Visual-HyDE).

### 💡 Bài học Kinh nghiệm (Key Lessons Learned)
- Kỹ thuật HyDE (Hypothetical Document Embeddings) trong không gian đa phương thức giúp thu hẹp khoảng cách ngữ nghĩa giữa ngôn ngữ tự nhiên của người dùng và đặc trưng thị giác của camera.

---

## 📅 Week 3: Frontend UX/UI Brutalist & Advanced Search Features

### 🎯 Mục tiêu Tuần (Weekly Objectives)
1. Thiết kế và hoàn thiện giao diện người dùng phong cách Neo-Brutalist trên React 19 + Tailwind CSS.
2. Tích hợp tính năng tua video theo thời gian thực (Interactive Video Clip Player with Range Seeking).
3. Xây dựng khay gom phân đoạn dữ liệu (Dataset Draft Tray) và công cụ xuất file JSONL / Zip.
4. Triển khai cơ chế thu thập phản hồi RLHF (Thích / Không thích) để tinh chỉnh độ liên quan.

### ✅ Kết quả Đã Hoàn Thành (Accomplishments)
- Hoàn thiện giao diện tìm kiếm `SearchPage.jsx`, hỗ trợ bộ lọc đa thuộc tính (Loại xe, Thời tiết, Ban ngày/Đêm, Biển báo giao thông).
- Xây dựng component `SceneCard.jsx` với modal xem trước video, highlight mốc thời gian (timeline timestamp) và thẻ nhãn chi tiết.
- Hoàn thiện khay lưu trữ `SelectionTray.jsx` và trang `DatasetDraftPage.jsx` cho phép kỹ sư AI gom các phân đoạn thú vị thành một tập dataset xuất khẩu.
- Tích hợp API RLHF `/api/v1/feedback` lưu dữ liệu preference vào PostgreSQL để phục vụ re-ranking sau này.
- Bản địa hóa toàn bộ giao diện sang tiếng Việt tự nhiên, chuyên nghiệp.

### ⚠️ Khó khăn & Thách thức (Challenges & Blockers)
- *Vấn đề:* Trình phát video khi tua tới các mốc thời gian 0.5s gặp lỗi giật lag do server không hỗ trợ Byte-Range requests.
- *Giải pháp:* Cấu hình Nginx Reverse Proxy và FastAPI Media Streaming hỗ trợ header `Range` và `If-Range` (`HTTP 206 Partial Content`).

### 💡 Bài học Kinh nghiệm (Key Lessons Learned)
- Trải nghiệm tua video tức thời (instant video seek) là yếu tố quyết định sự tiện dụng cho các kỹ sư gán nhãn xe tự hành khi duyệt hàng nghìn video.

---

## 📅 Week 4: APM Tracing, Full Benchmark, Docker & Cloud Run Multi-Container

### 🎯 Mục tiêu Tuần (Weekly Objectives)
1. Xây dựng hệ thống APM Trace Explorer nội bộ với biểu đồ Gantt Waterfall trong Admin.
2. Tích hợp bảng đánh giá Benchmark và mô tả Dataset BDD-100K / Golden Dataset vào Admin Control Center.
3. Đóng gói hoàn chỉnh hệ thống bằng Docker Compose đa dịch vụ và kiểm thử 100% unit tests.
4. Triển khai lên Google Cloud Run theo mô hình 1-Service Multi-Container Pod.

### ✅ Kết quả Đã Hoàn Thành (Accomplishments)
- Xây dựng `SystemTraceRecorder` (`app/core/tracer.py`) lưu vết chi tiết từng giai đoạn tìm kiếm (Parser, LLM, Embedding, Qdrant, Cache) trên bộ nhớ RAM với độ trễ < 0.1ms.
- Tạo giao diện `TraceExplorer.jsx` và `EvaluationBenchmark.jsx` hiển thị trực quan biểu đồ Gantt thời gian thực, KPI độ trễ P50/P95 và toàn bộ bảng so sánh mô hình.
- Thực hiện nghiên cứu bóc tách (Ablation Study) mô hình Cross-Encoder Reranker và đưa ra quyết định kỹ thuật tối ưu.
- Đạt **421 / 421 unit tests (100% PASS)** trên backend và **7 / 7 tests** trên frontend.
- Triển khai thành công lên Google Cloud Run: **`https://scenesearch-604840409374.asia-southeast1.run.app`** với 4 containers tích hợp.

### ⚠️ Khó khăn & Thách thức (Challenges & Blockers)
- *Vấn đề:* Cloud Run yêu cầu 1 URL public duy nhất trong khi hệ thống có 4 containers (Frontend, API, Embedding AI, Worker).
- *Giải pháp:* Áp dụng tính năng Multi-Container (Sidecar Pattern) của Cloud Run, cấu hình Frontend Nginx làm Ingress duy nhất trên cổng 80 và proxy nội bộ tới các container còn lại qua mạng `127.0.0.1`.

### 💡 Bài học Kinh nghiệm (Key Lessons Learned)
- Việc container hóa chặt chẽ và thiết lập pipeline multi-container giúp hệ thống dễ dàng chuyển đổi linh hoạt giữa môi trường local dev và Cloud Run production mà không cần thay đổi code base.
