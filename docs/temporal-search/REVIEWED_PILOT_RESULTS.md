# Kết quả pilot sau khi người dùng duyệt nhãn

Đây là báo cáo riêng 20 cặp pilot. Kết quả sau khi nhận thêm 100 nhãn đã duyệt
nằm ở [REVIEWED_EXPANSION_RESULTS.md](REVIEWED_EXPANSION_RESULTS.md).

Đánh giá ngày 14/11/2026 theo Asia/Saigon. Không chạy lại model, không train và
không thay đổi luồng cũ. Các query và video mục tiêu không đổi nên tái sử dụng
được 20 response baseline và 40 dự đoán QD/CG đã lưu trước khi duyệt.

## Kiểm tra dữ liệu

File người dùng: `data/temporal-search/group-b/pilot.reviewed.jsonl`.
SHA-256: `9950b5f4757a4ac273c14998b60e713b92d531051acd6e4e36a8ddb830f5b28d`.

- Đủ 20 query ID duy nhất, tất cả có human_verified=true và label_status human_verified.
- Có reviewer và reviewed_at; giữ nguyên file người dùng và nhãn sơ bộ gốc.
- Sau duyệt có 14 cặp dương và 6 cặp âm, tổng 15 khoảng sự kiện dương.
- 7 record đổi cửa sổ hoặc quan hệ. `pilot-03-02` đổi từ dương sang âm;
  `pilot-01-02` có hai khoảng `[3,5]` và `[27,35]`.
- Query, target video, source, duration và split không thay đổi.
- Validation có 2 video/8 cặp (6 dương, 2 âm); test có 3 video/12 cặp (8 dương, 4 âm).
  Split theo video, chưa chứng minh độc lập theo camera/chuyến đi.

Evaluator hiện từ chối nhãn chưa duyệt, tập rỗng, request annotation chưa có quan
hệ, baseline thiếu/lỗi HTTP, query đổi, prediction sai video hoặc artifact trùng.
Không biến request lỗi thành một retrieval miss. Với nhiều cửa sổ, R@1 dùng IoU
tốt nhất so với một trong các cửa sổ, không đo đã tìm đủ mọi cửa sổ.

## Khả năng lấy được video mục tiêu

| Split | Top 5 | Top 10 | Top 20 |
| --- | --- | --- | --- |
| Validation, 6 cặp dương | 2/6 | 3/6 | 3/6 |
| Test, 8 cặp dương | 1/8 | 1/8 | 1/8 |

Tổng top 20 chứa video mục tiêu đã gán nhãn ở 4/14 cặp dương. Các video khác
vẫn có thể đúng query nhưng chưa được gán nhãn. Vì vậy số này không phải recall
toàn corpus hoặc bằng chứng các video còn lại đều sai.

## Grounding khi đã được cung cấp video đúng

| Model | Validation mean IoU | Validation R@1 IoU>=0.5 | Test mean IoU | Test R@1 IoU>=0.5 |
| --- | --- | --- | --- | --- |
| QD-DETR CLIP-only | 0,282 | 1/6 | 0,292 | 1/8 |
| CG-DETR CLIP-only | 0,238 | 0/6 | 0,235 | 2/8 |

Cả hai có R@1 IoU>=0.7 bằng 0 trên validation và test của pilot. CG đạt nhiều
query test ở ngưỡng 0.5 hơn, QD có mean IoU cao hơn. Mẫu nhỏ và các chỉ số khác
nhau không đủ để chọn một model thắng tổng quát. Không chỉnh model/ngưỡng theo test.

Để so cùng điều kiện, chỉ xét 4 cặp dương có target đã được luồng cũ truy hồi.

| Split/tập con | Primary moment cũ mean IoU | QD mean IoU | CG mean IoU |
| --- | --- | --- | --- |
| Validation, 3 cặp có target | 0,224 | 0,320 | 0,231 |
| Test, 1 cặp có target | 0,250 | 0,292 | 0,291 |

Tập con một hoặc ba mẫu không chứng minh mức cải thiện production. Không so
mean IoU của bài toán đã có video đúng với hệ thống phải tìm video như hai bài
toán cùng điều kiện. Nhánh temporal end-to-end chưa được triển khai trong nhóm B.

## Phân tích lỗi và điểm số

Trên 20 cặp, top-1 QD phủ >=80% video ở 16 cặp, CG ở 12 cặp. Trên 14 cặp
dương, mỗi model có 12 cặp top-1 chưa đạt IoU 0.5. Điều này cho thấy trả đoạn
rộng chưa giải quyết nhu cầu định vị sự kiện ngắn trong dashcam.

Trên 6 cặp âm đã duyệt, điểm top-1 >=0.5 xuất hiện ở QD 6/6 và CG 5/6. Đây là
diagnostic của proposal score, không phải xác suất đúng hoặc false-positive
rate toàn corpus. Chưa chọn threshold phục vụ.

Phân tích threshold chỉ dùng validation, không dùng nhãn test để chọn ngưỡng.
Đoạn QD định vị đúng duy nhất tại IoU 0.5 có score 0,984521, thấp hơn một cặp
âm score 0,985958. Vì vậy một cutoff tăng dần không thể vừa giữ đoạn đúng đó
vừa loại cả hai cặp âm validation. CG chưa có top-1 đạt IoU 0.5 trên validation.
Chỉ nâng ngưỡng score không sửa được lỗi localization quan sát được ở đây.

Chi tiết ở `reviewed-label-analysis.json` và `reviewed-errors.csv` trong thư mục
data nhóm B. Các cờ lỗi có thể trùng nhau, không cộng các cột như nhóm rời nhau.

## Quyết định cho nhóm B

- Hoàn thành đánh giá pilot bằng 20 nhãn người dùng đã duyệt.
- Giữ nguyên luồng cũ. Chưa đưa QD/CG checkpoint nguyên bản vào phục vụ.
- Ưu tiên kiểm tra candidate recall của nhánh mới và cách từ chối query không
  phù hợp, đồng thời mở rộng nhãn trước khi quyết định fine-tune.
- Có code train và checkpoint chạy được không đồng nghĩa checkpoint đã tốt
  trên dashcam. Chưa có phép train thật để báo thời gian/epoch trên máy này.
- Bộ mở rộng đã được người dùng duyệt: 79 dương/21 âm trên 20 video mới.
  Đã chạy baseline/checkpoint mới và hoàn tất bộ đánh giá 120 cặp; các số trong
  báo cáo này vẫn chỉ mô tả pilot ban đầu.

## Artifact và cách chạy lại

Report: `data/temporal-search/group-b/human-diagnostics.json` có fingerprint
nhãn, nhãn tham chiếu, baseline và predictions để kiểm tra khả năng tái sử dụng.

```powershell
python temporal-search/evaluation/evaluate_pilot.py --labels data/temporal-search/group-b/pilot.reviewed.jsonl --baseline data/temporal-search/group-b/legacy-baseline.jsonl --predictions data/temporal-search/group-b/grounding-cpu/predictions.jsonl --output data/temporal-search/group-b/human-diagnostics.json
python temporal-search/evaluation/analyze_reviewed_pilot.py --labels data/temporal-search/group-b/pilot.reviewed.jsonl --reference-labels temporal-search/evaluation/pilot.provisional.jsonl --baseline data/temporal-search/group-b/legacy-baseline.jsonl --predictions data/temporal-search/group-b/grounding-cpu/predictions.jsonl --output-dir data/temporal-search/group-b
```

Hướng dẫn mở rộng ở [EXPANSION_REVIEW.md](EXPANSION_REVIEW.md). Số đo CPU vẫn là
số đo ở [EXPERIMENT_RESULTS.md](EXPERIMENT_RESULTS.md), không suy ra benchmark
mới từ việc chấm lại nhãn.
