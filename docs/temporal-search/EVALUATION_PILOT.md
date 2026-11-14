# Pilot đánh giá query–video–thời gian

Đã nhận `pilot.reviewed.jsonl` do người dùng xác nhận đủ 20 nhãn. Kết quả hiện
tại ở [REVIEWED_PILOT_RESULTS.md](REVIEWED_PILOT_RESULTS.md): 14 cặp dương/6 cặp
âm và 7 record đã đổi. File provisional dưới đây là bản tham chiếu lịch sử,
được giữ nguyên để kiểm tra query/video identity của các dự đoán đã có.

## Dữ liệu hiện có

[`pilot.provisional.jsonl`](../../temporal-search/evaluation/pilot.provisional.jsonl)
gồm 20 cặp trên 5 video đầu tiên đã ingest thành công, chọn theo thứ tự tên file.
Có 15 cặp dương và 5 cặp âm theo video. Hai video thuộc validation, ba video
thuộc test; một video không xuất hiện ở cả hai split.

Nhãn do trợ lý xem source frames đã sửa hướng, lấy mẫu cách 2 giây. Mọi record
có `human_verified=false`, `label_status=provisional_assistant_visual` và
`boundary_uncertainty_s=2`. Đây không phải nhãn gold hoặc mẫu đại diện ngẫu nhiên
cho 1000 video. Không dùng caption, metadata fallback hoặc dự đoán model để tạo
các khoảng nhãn. Bản dịch Việt được lưu UTF-8 riêng và ghép vào records.

Pilot và 100 cặp mở rộng đều đã được người dùng duyệt. Tổng 120 cặp/25 video
đã được chấm ở [REVIEWED_EXPANSION_RESULTS.md](REVIEWED_EXPANSION_RESULTS.md).
Quy trình bộ mở rộng ở [EXPANSION_REVIEW.md](EXPANSION_REVIEW.md).

## Trang duyệt và cách xác nhận

Mở file local `data/temporal-search/group-b/annotation-review.html` khi stack cũ
đang chạy. Trang gồm playback đầy đủ từ API hiện tại, contact sheets và query.
Không hiển thị dự đoán model để giảm ảnh hưởng lên người gán nhãn.

1. Nhập tên người duyệt, xem video đúng hướng, kiểm tra nội dung và thời điểm.
2. Sửa các khoảng giây hoặc đổi cặp thành âm nếu query không xuất hiện.
3. Chọn xác nhận đã xem video và xác nhận từng nhãn. Không ô nào tự đánh dấu.
4. Xuất `pilot.reviewed.jsonl`. Record chưa xác nhận vẫn giữ trạng thái sơ bộ.
5. Lưu bản xuất vào `data/temporal-search/group-b/pilot.reviewed.jsonl`.

Với chuyển động như chuyển làn/dừng/chạy ngang, xem liên tục quanh sự kiện,
không chỉ dựa vào ảnh. Nhãn dương là các khoảng tối thiểu đủ mô tả sự kiện,
không kéo dài để làm khớp dự đoán. Một query có thể có nhiều khoảng.
Nhãn âm chỉ khẳng định trong video này; không áp dụng ra toàn kho.

Chạy lại đánh giá sau khi đủ nhãn người duyệt:

```powershell
python temporal-search/evaluation/evaluate_pilot.py --labels data/temporal-search/group-b/pilot.reviewed.jsonl --baseline data/temporal-search/group-b/legacy-baseline.jsonl --predictions data/temporal-search/group-b/grounding-cpu/predictions.jsonl --output data/temporal-search/group-b/human-diagnostics.json
```

Công cụ mặc định từ chối nếu còn bất kỳ record chưa human-verified. Có thể chạy
`--allow-provisional` để xem diagnostics sơ bộ, nhưng report luôn ghi rõ không
phải gold. Không chỉ sửa cờ human_verified để bỏ qua bước xem video.

## Ý nghĩa các phép đo

- `legacy_designated_target_hit@K`: tỷ lệ video mục tiêu đã biết xuất hiện trong
  K kết quả. Nhãn không đầy đủ toàn kho nên đây không phải recall/precision
  toàn corpus; video khác trả về vẫn có thể là đáp án đúng chưa gán nhãn.
- `legacy_designated_target_primary_window`: IoU đoạn chính nếu đúng target
  được trả, bằng 0 khi target không được trả. Không coi video khác là false
  positive nếu chưa có nhãn cho video đó.
- `grounding_given_target_video`: model được cung cấp sẵn video mục tiêu. Đây
  là bài toán định vị có điều kiện, không phải luồng search mới end-to-end.
- `when_legacy_target_retrieved`: tập con chung để tránh so bài toán đã biết
  video với bài toán phải tìm video như thể cùng điều kiện.
- Điểm top-1 trên các cặp âm và số điểm >0.5 chỉ là diagnostics của score.
  Ngưỡng này chưa hiệu chỉnh và không phải corpus false-positive rate.

Tính mean IoU và R@1 tại IoU 0.3/0.5/0.7 cho các cặp dương. Không báo mAP toàn
kho khi nhãn chưa đủ. Validation dùng chọn cấu hình; test chỉ báo cáo, không
điều chỉnh theo từng lỗi test.

## Mở rộng sau pilot

Sau khi duyệt, mở rộng từ 20 lên 100–200 query, lấy thêm video theo nhóm ngày/
đêm, đường phố/đường cao tốc, nhiều/ít đối tượng và sự kiện ngắn/dài. Tránh chỉ
chọn những query model làm tốt. Chia theo video và chuyến đi nếu có thông tin.
Dùng người thứ hai kiểm tra một phần nhãn, ghi bất đồng và quy tắc xử lý.
