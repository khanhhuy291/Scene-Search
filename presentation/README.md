# 🎯 SceneSearch (P-081) — Pitch Deck & Video Demo Guidelines

This directory contains the presentation assets, pitch deck structure, and video demo script for **SceneSearch (P-081)**.

---

## 1. 📊 10-Slide Pitch Deck Structure

| Slide # | Slide Title | Core Message & Talking Points | Visual Assets |
| :---: | :--- | :--- | :--- |
| **01** | **Title & Vision** | **SceneSearch (P-081):** Nền tảng tìm kiếm ngữ nghĩa đa phương thức cho video xe tự hành (Multimodal Driving-Scene Search & Slicing Engine). | Logo, Hero screenshot |
| **02** | **The Problem** | Dữ liệu video xe tự hành (BDD-100K, Waymo) khổng lồ (hàng trăm TB); kỹ sư AI mất hàng giờ tua thủ công để tìm các tình huống hiếm (Edge Cases: người cầm dù trời mưa, xe cắt đầu ban đêm, đèn chớp khẩn cấp). | Pain points diagram |
| **03** | **The Solution** | Tìm kiếm video bằng ngôn ngữ tự nhiên (Tiếng Việt / Tiếng Anh); trích xuất chính xác đến từng giây (0.5s timestamp); tự động làm mờ mặt và biển số xe bảo vệ quyền riêng tư (GDPR compliant). | Solution highlight box |
| **04** | **Product Demo** | Giao diện Neo-Brutalist trực quan; Instant Video Seeking; Bộ lọc thuộc tính đa tầng (thời tiết, mật độ xe, loại đường, biển báo). | Live UI Screenshots |
| **05** | **Dataset Slicing & Export** | Khay gom dữ liệu (Dataset Draft Tray) cho phép kỹ sư AI tạo lát cắt dữ liệu (custom slice) và tải về tệp manifest `JSONL` + gói `ZIP` ảnh cho PyTorch / HuggingFace. | Dataset export flow |
| **06** | **System Architecture** | Kiến trúc Multi-Container Pod trên Google Cloud Run: Frontend Ingress (Nginx Port 80) -> FastAPI (Port 8000) -> Qwen3-VL Embedding Service (Port 8001) -> Celery Ingestion Worker. | Mermaid Architecture Diagram |
| **07** | **Tri-Tier Agentic Search** | **Tier 1:** Domain Guardrail (chặn truy vấn ngoài ngành) -> **Tier 2:** Visual-HyDE (mở rộng góc nhìn camera kính lái) -> **Tier 3:** Reflection Loop (nới lỏng điều kiện khi zero-hit). | Tri-Tier flowchart |
| **08** | **Benchmark & Evaluation** | Đánh giá trên 88 Golden Queries BDD-100K 20GB: Qwen3-VL đạt **89.77% Hit@5**, **0.8016 MRR** (vượt trội +627% so với SigCLIP baseline); Nghiên cứu bóc tách Reranker (Ablation study). | Benchmark comparison table |
| **09** | **APM Traces & Observability** | Trình khám phá vết APM nội bộ (Trace Explorer) với biểu đồ Gantt Waterfall thời gian thực, đo độ trễ sub-millisecond trên RAM. | Gantt timeline screenshot |
| **10** | **Live Deployment & Team** | Official Domain: `https://c3-app-081.vinai.io.vn/` (Cloud Run: `https://scenesearch-604840409374.asia-southeast1.run.app`); 421/421 Unit Tests Passed; Giới thiệu đội ngũ kỹ sư. | Team & QR Code Live URL |

---

## 2. 🎥 5-Minute Video Demo Script (Kịch Bản Quay Video Demo)

- **00:00 - 00:45 (Vấn đề & Giới thiệu):**
  - Giới thiệu bài toán tìm kiếm khung cảnh xe tự hành và khó khăn khi duyệt hàng ngàn giờ video dashcam.
  - Giới thiệu **SceneSearch (P-081)**.
- **00:45 - 02:00 (Live Search Demo & Trải nghiệm):**
  - Thực hiện tìm kiếm bằng tiếng Việt: *"xe toyota màu xanh rẽ trái cạnh cầu vượt"*.
  - Thể hiện khả năng Visual-HyDE và trả về kết quả chính xác trong < 200ms.
  - Mở modal xem video, chứng minh tính năng tua tức thời (Byte-range seek) đến đúng giây xảy ra sự kiện.
  - Chỉ ra tính năng tự động làm mờ biển số và khuôn mặt trên khung hình.
- **02:00 - 03:15 (Dataset Slicing & Export):**
  - Chọn các kết quả video và bấm *"Thêm vào bản nháp dataset"*.
  - Chuyển sang trang **Bản nháp Dataset**, tùy chỉnh tiêu đề và tải về gói file `JSONL` + `ZIP` ảnh đã ẩn danh.
- **03:15 - 04:15 (Admin Control Center, APM Traces & Benchmarks):**
  - Mở trang Admin: Trình diễn **APM Trace Explorer** với biểu đồ Gantt phân tích độ trễ từng micro-span (LLM, Qdrant, Embedding).
  - Trình diễn tab **Đánh giá & Benchmark** với số liệu kiểm thử trên tập 88 Golden Queries và chi tiết tập dữ liệu BDD-100K 20GB.
- **04:15 - 05:00 (Kiến trúc, Deployment & Kết luận):**
  - Tổng kết kiến trúc Multi-Container trên Google Cloud Run và chứng chỉ kiểm thử 421/421 tests passed.
  - Kêu gọi truy cập Live Demo.

---

## 3. 🔗 Official Delivery Links

- 🌐 **Official Live Domain:** [https://c3-app-081.vinai.io.vn/](https://c3-app-081.vinai.io.vn/) *(Cloud Run: [https://scenesearch-604840409374.asia-southeast1.run.app](https://scenesearch-604840409374.asia-southeast1.run.app))*
- 🎥 **Video Demo (Google Drive):** [https://drive.google.com/file/d/1gXYMA_KUQKXAMoWqEM4tfmlxS2FZBpq8/view?usp=sharing](https://drive.google.com/file/d/1gXYMA_KUQKXAMoWqEM4tfmlxS2FZBpq8/view?usp=sharing)
- 📊 **Pitch Deck Slide (Google Drive):** [https://drive.google.com/file/d/12VwYiEgA-HEAYQIE1Vo7gIWLeQOJIMpq/view?usp=sharing](https://drive.google.com/file/d/12VwYiEgA-HEAYQIE1Vo7gIWLeQOJIMpq/view?usp=sharing)
