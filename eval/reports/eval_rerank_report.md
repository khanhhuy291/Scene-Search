# 📊 Báo Cáo Đánh Giá Hiệu Năng: Trước & Sau Rerank (Top-K = 10, Tolerance = ±4 frames)

> **Tập dữ liệu Ground Truth:** `app/eval/golden_set/eval.csv`
> **Tổng số câu truy vấn kiểm thử:** `88` queries
> **Mô hình Giai đoạn 1 (First-Stage Vector Search):** `Qwen/Qwen3-VL-Embedding-2B`
> **Mô hình Giai đoạn 2 (Second-Stage Cross-Encoder Reranker):** `Qwen/Qwen3-VL-Reranker-2B`
> **Thời gian thực thi:** Vector Search: `90.03s` | Reranking: `116.32s`

---

## 1. Bảng So Sánh Tổng Hợp (Retrieval Metrics: Before vs After Rerank)

| Cấp độ đánh giá              | Chỉ số (Metric) | Trước Rerank (Qwen3-VL-Embedding-2B) | Sau Rerank (Qwen3-VL-Reranker-2B) | Độ cải thiện (Delta) |
|------------------------------|-----------------|--------------------------------------|-----------------------------------|----------------------|
| 🎬 Video-Level (Đúng Video)   | Hit@1           | 72.73%                               | 65.91%                            | -6.82%               |
| 🎬 Video-Level (Đúng Video)   | Hit@3           | 84.09%                               | 82.95%                            | -1.14%               |
| 🎬 Video-Level (Đúng Video)   | Hit@5           | 88.64%                               | 90.91%                            | +2.27%               |
| 🎬 Video-Level (Đúng Video)   | Hit@10          | 93.18%                               | 93.18%                            | +0.00%               |
| 🎬 Video-Level (Đúng Video)   | Hit@20          | 93.18%                               | 93.18%                            | +0.00%               |
| 🎬 Video-Level (Đúng Video)   | Hit@50          | 93.18%                               | 93.18%                            | +0.00%               |
| 🎬 Video-Level (Đúng Video)   | MRR@5           | 0.7886                               | 0.7455                            | -0.0432              |
| 🎬 Video-Level (Đúng Video)   | MRR@10          | 0.7953                               | 0.7490                            | -0.0463              |
| 🎬 Video-Level (Đúng Video)   | MRR (Full)      | 0.7953                               | 0.7490                            | -0.0463              |
| 🎯 Frame-Tolerant (±4f / ~2s) | Hit@1           | 60.23%                               | 55.68%                            | -4.55%               |
| 🎯 Frame-Tolerant (±4f / ~2s) | Hit@3           | 77.27%                               | 75.00%                            | -2.27%               |
| 🎯 Frame-Tolerant (±4f / ~2s) | Hit@5           | 85.23%                               | 88.64%                            | +3.41%               |
| 🎯 Frame-Tolerant (±4f / ~2s) | Hit@10          | 90.91%                               | 90.91%                            | +0.00%               |
| 🎯 Frame-Tolerant (±4f / ~2s) | Hit@20          | 90.91%                               | 90.91%                            | +0.00%               |
| 🎯 Frame-Tolerant (±4f / ~2s) | Hit@50          | 90.91%                               | 90.91%                            | +0.00%               |
| 🎯 Frame-Tolerant (±4f / ~2s) | MRR@5           | 0.6981                               | 0.6676                            | -0.0305              |
| 🎯 Frame-Tolerant (±4f / ~2s) | MRR@10          | 0.7064                               | 0.6705                            | -0.0359              |
| 🎯 Frame-Tolerant (±4f / ~2s) | MRR (Full)      | 0.7064                               | 0.6705                            | -0.0359              |
| 🖼️ Frame-Exact (Đúng Frame)  | Hit@1           | 38.64%                               | 37.50%                            | -1.14%               |
| 🖼️ Frame-Exact (Đúng Frame)  | Hit@3           | 60.23%                               | 60.23%                            | +0.00%               |
| 🖼️ Frame-Exact (Đúng Frame)  | Hit@5           | 71.59%                               | 73.86%                            | +2.27%               |
| 🖼️ Frame-Exact (Đúng Frame)  | Hit@10          | 81.82%                               | 81.82%                            | +0.00%               |
| 🖼️ Frame-Exact (Đúng Frame)  | Hit@20          | 81.82%                               | 81.82%                            | +0.00%               |
| 🖼️ Frame-Exact (Đúng Frame)  | Hit@50          | 81.82%                               | 81.82%                            | +0.00%               |
| 🖼️ Frame-Exact (Đúng Frame)  | MRR@5           | 0.5059                               | 0.4983                            | -0.0076              |
| 🖼️ Frame-Exact (Đúng Frame)  | MRR@10          | 0.5199                               | 0.5093                            | -0.0106              |
| 🖼️ Frame-Exact (Đúng Frame)  | MRR (Full)      | 0.5199                               | 0.5093                            | -0.0106              |

---

## 2. Phân Tích Thống Kê Thay Đổi Thứ Hạng (Ranking Shift Analysis)

* **🎯 Cấp độ Frame-Tolerant (±4 frames / ~2 giây):**
  * **Cải thiện thứ hạng (Improved):** `16/88` queries (`18.2%`)
  * **Không đổi (Unchanged):** `51/88` queries (`58.0%`)
  * **Thứ hạng giảm (Degraded):** `21/88` queries (`23.9%`)

* **🖼️ Cấp độ Frame-Exact (Đúng chính xác Frame):**
  * **Cải thiện thứ hạng (Improved):** `22/88` queries (`25.0%`)
  * **Không đổi (Unchanged):** `45/88` queries (`51.1%`)
  * **Thứ hạng giảm (Degraded):** `21/88` queries (`23.9%`)

* **🎬 Cấp độ Video-Level (Đúng Video cha):**
  * **Cải thiện thứ hạng (Improved):** `12/88` queries (`13.6%`)
  * **Không đổi (Unchanged):** `59/88` queries (`67.0%`)
  * **Thứ hạng giảm (Degraded):** `17/88` queries (`19.3%`)

---

## 3. Mẫu Một Số Câu Truy Vấn Được Cải Thiện Thứ Hạng Nổi Bật

| Query ID | Câu truy vấn (Caption)                                | GT Video          | GT Frame        | Video Rank | Tolerant Rank (±4f) | Exact Frame Rank |
|----------|-------------------------------------------------------|-------------------|-----------------|------------|---------------------|------------------|
| #4960    | A white SUV drives on a street with a green traffi... | 006fdb67-526bb14e | frame_00002.jpg | #8 ➔ #1    | #8 ➔ #1             | #8 ➔ #1          |
| #1       | Xe Toyota xanh ở giữa, xe đen bên phải, cầu vượt b... | 0000f77c-6257be58 | frame_00000.jpg | #1 ➔ #3    | #7 ➔ #3             | #7 ➔ #3          |
| #14916   | Nighttime urban street with a silver pickup truck ... | 0135988f-6e5c56c0 | frame_00024.jpg | #5 ➔ #1    | #5 ➔ #1             | #5 ➔ #1          |
| #18384   | A nighttime view from a car shows a black SUV dire... | 01853f47-6975b587 | frame_00000.jpg | #6 ➔ #2    | #6 ➔ #2             | #6 ➔ #2          |
| #20355   | A nighttime wet city intersection with red traffic... | 01ad8d8a-49bb0c93 | frame_00017.jpg | #1 ➔ #1    | #5 ➔ #1             | #- ➔ #-          |
| #25069   | A sunny daylight view down a residential street li... | 021c4a16-1c50e818 | frame_00068.jpg | #8 ➔ #4    | #8 ➔ #4             | #9 ➔ #4          |
| #2       | A view from a car shows a dark blue Toyota Highlan... | 0000f77c-6257be58 | frame_00002.jpg | #1 ➔ #1    | #4 ➔ #1             | #7 ➔ #1          |
| #20368   | Nighttime wet city street scene with red traffic l... | 01ad8d8a-49bb0c93 | frame_00047.jpg | #4 ➔ #1    | #4 ➔ #1             | #5 ➔ #1          |
| #22481   | A nighttime view from a vehicle on a steel truss b... | 01d87368-2ac1d81d | frame_00066.jpg | #1 ➔ #1    | #4 ➔ #1             | #4 ➔ #1          |
| #1539    | A view down a city street with double yellow cente... | 002ab96a-a96704f9 | frame_00024.jpg | #3 ➔ #2    | #3 ➔ #2             | #3 ➔ #2          |
| #2795    | From a car's perspective, a grey sedan is visible ... | 003baca5-d6cd84e5 | frame_00009.jpg | #2 ➔ #1    | #2 ➔ #1             | #- ➔ #-          |
| #3708    | View from a car driving under an overpass on a cit... | 0051e391-d32a618e | frame_00045.jpg | #2 ➔ #1    | #2 ➔ #1             | #2 ➔ #1          |
| #5927    | Sunny daytime highway with a black sedan in the ri... | 007c11bf-f6da335c | frame_00052.jpg | #2 ➔ #1    | #2 ➔ #1             | #- ➔ #-          |
| #16647   | Nighttime urban street with a brightly illuminated... | 015b88d3-48cc2dc4 | frame_00044.jpg | #4 ➔ #3    | #4 ➔ #3             | #4 ➔ #3          |
| #21717   | A gray minivan is parked on the left side of the s... | 01ce3717-4aa554ab | frame_00014.jpg | #1 ➔ #1    | #3 ➔ #2             | #3 ➔ #2          |

---

## 4. Đánh Giá & Nhận Xét Chuyên Môn

1. **Hiệu năng First-Stage Vector Search:**
   - Vector Embedding của Qwen 2B cho khả năng tìm kiếm video thô rất tốt với **Hit@50 = 93.18%** và **Hit@1 = 72.73%**.
2. **Hiệu quả Reranker trên Metric nới lỏng (Tolerance = ±4 frames):**
   - Với độ lệch cho phép 4 frames (~2 giây), Reranker đạt **Hit@1 = 55.68%** (thay đổi -4.55% so với trước khi rerank).
   - Chỉ số **MRR Tolerant** đạt **0.6705**, phản ánh chân thực trải nghiệm tra cứu video trong thực tế khi frame trả về nằm đúng phân đoạn hành động.
