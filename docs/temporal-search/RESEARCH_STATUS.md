# Trạng thái nghiên cứu và checkpoint

Cập nhật ngày 14/11/2026, Asia/Saigon.

Nhóm B đã hoàn thành trong phạm vi khảo sát, bộ đánh giá và kiểm chứng CPU.
Đã nhận cả hai file nhãn người dùng; không còn chờ duyệt bộ mở rộng.
Điều kiện đưa checkpoint nguyên bản vào phục vụ chưa đạt.

| Nhiệm vụ | Sản phẩm đã hoàn thành | Giới hạn |
| --- | --- | --- |
| B4. Dữ liệu và baseline | 120 cặp đã duyệt/25 video, 93 dương/27 âm, chia validation/test theo video; 120 response baseline và phân tích lỗi video/đoạn | Nhãn theo cặp chọn trước, chưa exhaustive toàn kho; một reviewer, chưa bảo đảm độc lập chuyến đi |
| B5. Paper/repo/train/checkpoint | Khảo sát Moment-DETR, QD-DETR, CG-DETR, UniVTG, FlashVTG; pin source, kiểm code train/feature, kiểm hash và nạp strict QD/CG CLIP-only | Không chạy toàn bộ năm model; có code train chưa đồng nghĩa đã đo fine-tune |
| B6. Chạy checkpoint riêng | 25 video/240 predictions QD/CG, đo các stage CPU/RSS, báo cáo chia tập và trang xem lại dự đoán | GPU chưa đo; chưa train hoặc benchmark temporal search end-to-end |

## Kết quả quyết định

Trên test gộp có 55 cặp dương, luồng cũ lấy được target trong top 20 ở 9/55.
Khi được cho sẵn video đúng, QD đạt IoU≥0,5 ở 3/55, CG ở 8/55.
Trên 27 cặp âm toàn bộ dữ liệu, QD có điểm >0,5 ở 27 cặp, CG ở 26.
Không dùng các số này để suy ra precision/recall toàn kho hoặc cải thiện end-to-end.

Giữ QD làm baseline kỹ thuật, CG làm đối chứng. Chưa chọn checkpoint phục vụ.
Bước nghiên cứu tiếp theo là prototype giới hạn C7–C8 để kiểm tra đặc trưng và
truy hồi ứng viên riêng, rồi mới đánh giá tiếp grounding/từ chối kết quả sai.
Chưa mở rộng cache toàn kho hoặc tích hợp đầy đủ C9/D khi gate chất lượng chưa đạt.
Train thuộc E14 và cần số đo thực tế trước khi ước lượng thời gian.

## Tài liệu và artifact

- [Kết quả đầy đủ sau 120 nhãn](REVIEWED_EXPANSION_RESULTS.md).
- [Kết quả riêng pilot 20 nhãn](REVIEWED_PILOT_RESULTS.md).
- [Khảo sát mô hình, code train và checkpoint](MODEL_RESEARCH.md).
- [Cách thu bộ mở rộng và chạy lại](EXPANSION_REVIEW.md).
- [Nguồn và môi trường thực nghiệm](RESEARCH_REPRODUCTION.md).
- [Phiên pilot ban đầu](EXPERIMENT_RESULTS.md).
- Báo cáo máy đọc được: `data/temporal-search/group-b/reviewed-evaluation/`.
- Xem lại: `data/temporal-search/group-b/reviewed-evaluation/checkpoint-review.html`.

Giữ nguyên 341 file thuộc luồng cũ theo snapshot nguồn trước nghiên cứu.
Các thao tác search dùng API hiện có; không restart, reindex, migrate hoặc thay
model/Compose của ứng dụng. Nhãn gốc và các kết quả pilot trước đây được giữ riêng.
