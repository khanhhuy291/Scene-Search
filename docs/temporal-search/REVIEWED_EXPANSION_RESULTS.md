# Kết quả nhóm B sau khi duyệt đủ 120 cặp

Ngày thực hiện: 14/11/2026, Asia/Saigon.

Đã hoàn thành B4–B6 trong phạm vi nghiên cứu và chạy CPU: có bộ nhãn đã duyệt,
baseline luồng cũ, khảo sát năm mô hình và hai checkpoint chạy được trên video
dự án. Kết quả chưa đạt điều kiện đưa checkpoint nguyên bản vào phục vụ.
Luồng tìm kiếm cũ tiếp tục hoạt động; chưa train hoặc triển khai API temporal.

## Dữ liệu và tính toàn vẹn

Nhận 100 nhãn mở rộng do người dùng duyệt: 79 dương/21 âm trên 20 video.
Có 4 query tiếng Anh được sửa và 36 record đổi quan hệ/khoảng thời gian.
Toàn bộ baseline và predictions mở rộng được chạy sau khi chốt các chỉnh sửa.
Giữ nguyên file nhãn người dùng; không đổi cờ xác nhận hoặc thời gian để khớp model.

- Pilot: 20 cặp, 14 dương/6 âm trên 5 video.
- Mở rộng: 100 cặp, 79 dương/21 âm trên 20 video khác.
- Gộp: 120 query tiếng Anh khác nhau, 93 dương/27 âm trên 25 video.
- Có 101 khoảng đúng, 7 cặp có nhiều khoảng không liên tục.
- Một người duyệt; chưa đo độ đồng thuận giữa nhiều người.

| Split | Video | Cặp | Dương | Âm |
| --- | --- | --- | --- | --- |
| validation | 10 | 48 | 38 | 10 |
| test | 15 | 72 | 55 | 17 |

Không video nào xuất hiện ở cả validation và test. Video mở rộng không trùng
video/prefix của pilot. Chưa có thông tin để bảo đảm độc lập theo chuyến đi/camera.
100 query mở rộng được viết theo frame nguồn rồi người dùng duyệt toàn video,
không lấy caption tự động hoặc prediction model làm đáp án.

SHA-256 nhãn gốc:

- `pilot.reviewed.jsonl`: `9950b5f4757a4ac273c14998b60e713b92d531051acd6e4e36a8ddb830f5b28d`.
- `expansion.reviewed.jsonl`: `0b43b242e43d1b1918980c60dcbc0b1a82c854da7d25efb055f978f60ce5c51b`.

## B4 — Baseline của luồng cũ

Thu mới 100 response HTTP 200, dùng đúng query người dùng đã sửa, limit=20,
giữ default search/rerank/agentic. Cộng với 20 response pilot đã có: 120 response.
Không đổi index hoặc sửa bộ lọc của ứng dụng.

| Bộ gộp, cặp dương | Target trong top 5 | Top 10 | Top 20 |
| --- | --- | --- | --- |
| validation | 6/38 | 7/38 | 8/38 |
| test | 6/55 | 7/55 | 9/55 |

Tổng target hit@20 là 17/93. Riêng bộ mở rộng là 13/79 (validation 5/32,
test 8/47). Đây là khả năng lấy được **video mục tiêu đã gán nhãn**,
không phải recall/precision toàn corpus: các video khác trả về vẫn có thể phù hợp.

Có 64/100 request mở rộng trả danh sách rỗng, trong đó 46/79 cặp dương.
Trên bộ gộp, có 51/93 cặp dương trả rỗng; cả 51 response đều có
`unconfirmed_concepts`. Trường này là dấu hiệu chẩn đoán từ backend, chưa phải
thử nghiệm loại bỏ từng thành phần để chứng minh nguyên nhân duy nhất.
Ví dụ query biển STOP có thêm yêu cầu `intersection/residential`; query xe van
đỏ được diễn giải thành `truck/clear_sky/urban` và có concept chưa xác nhận.

Grounding không thể khôi phục video mục tiêu nếu bước ứng viên đã bỏ sót.
Nhánh mới cần đo truy hồi riêng ở C8; không bỏ bộ lọc hay sửa engine cũ trong B.

## B5–B6 — Checkpoint và kết quả định vị

Khảo sát Moment-DETR, QD-DETR, CG-DETR, UniVTG và FlashVTG, gồm code train,
feature requirements và checkpoint, ở [MODEL_RESEARCH.md](MODEL_RESEARCH.md).
Đã kiểm hash và nạp strict checkpoint CLIP-only chính thức của QD-DETR/CG-DETR.
Giữ nguyên checkpoint và preprocessing đã khóa; không chọn ngưỡng theo test.

Chạy mới 200 lần grounding trên bộ mở rộng; cộng pilot là 240 predictions.
Bảng dưới dùng top-1 proposal của model khi **đã được cung cấp video đúng**.

| Bộ gộp | Model | Mean IoU | R@1 IoU≥0,3 | R@1 IoU≥0,5 | R@1 IoU≥0,7 |
| --- | --- | --- | --- | --- | --- |
| validation | qd_detr | 0,277 | 16/38 | 4/38 | 1/38 |
| validation | cg_detr | 0,276 | 16/38 | 6/38 | 1/38 |
| test | qd_detr | 0,238 | 21/55 | 3/55 | 1/55 |
| test | cg_detr | 0,274 | 23/55 | 8/55 | 5/55 |

IoU là độ giao/chia hợp của đoạn dự đoán và đoạn đúng. Khi có nhiều khoảng nhãn,
R@1 tính khớp với một khoảng bất kỳ, chưa đo tìm đủ mọi lần xuất hiện.

Riêng bộ mở rộng, test có 47 cặp dương: QD mean IoU 0,229,
R@1 IoU≥0,5 là 2/47; CG mean IoU 0,280,
R@1 IoU≥0,5 là 6/47. Điểm gộp không phải một lần kiểm định hoàn toàn mới:
pilot đã được phân tích trước và hai bộ có cách chọn video/query khác nhau.

## So sánh trên cùng tập con có video được truy hồi

| Bộ gộp | Cặp có target trong top 20 | Đoạn chính cũ mean IoU | QD mean IoU | CG mean IoU |
| --- | --- | --- | --- | --- |
| validation | 8 | 0,208 | 0,205 | 0,172 |
| test | 9 | 0,158 | 0,266 | 0,314 |

Trên 9 cặp test này, số đạt IoU≥0,5 là luồng cũ 0/9, QD 0/9, CG 1/9.
Tập con nhỏ, phụ thuộc bộ query và chỉ so đoạn chính/top-1. Chưa có luồng temporal
end-to-end để kết luận cải thiện chất lượng hoặc tốc độ toàn hệ thống.

## Lỗi đoạn dài và query âm

Trên 120 cặp, QD trả top-1 phủ ít nhất 80% video ở 97 cặp; CG ở 82 cặp.
Trên 93 cặp dương, QD chưa đạt IoU 0,5 ở 86 cặp; CG ở 79 cặp.

Các sự kiện ngắn là vấn đề rõ nhất. Nhóm dưới đây có khoảng nhãn dài nhất không
quá 10 giây, không phải ngưỡng được dùng để chọn model hoặc chỉnh đầu ra.

| Bộ gộp | Cặp sự kiện ngắn | QD đạt IoU≥0,5 | CG đạt IoU≥0,5 |
| --- | --- | --- | --- |
| validation | 22 | 1/22 | 1/22 |
| test | 31 | 0/31 | 2/31 |

Trên 27 cặp âm, QD có top-1 score >0,5 ở 27/27, CG ở 26/27. Riêng test là
QD 17/17 và CG 16/17. Đây là score diagnostic, không phải xác suất đúng,
false-positive rate toàn kho hoặc ngưỡng từ chối đã được hiệu chỉnh.
Nhiều câu âm là đối chứng dễ về ngày/đêm/tuyết; không dùng chúng thay benchmark âm khó.

Phân tích cutoff chỉ dùng validation (38 dương/10 âm). CG có điểm âm cao nhất
0,995208, cao hơn mọi đoạn định vị đúng tại IoU 0,5, nên không có một cutoff
tăng dần vừa giữ một đoạn đúng vừa loại toàn bộ âm validation đã biết.
QD có thể giữ ít nhất một đoạn đúng với cutoff rất cao, nhưng không giải quyết
việc phần lớn sự kiện bị định vị sai; chưa chọn cutoff để triển khai.
Các bảng score và lỗi từng câu nằm trong artifact bên dưới.

## Tài nguyên và thời gian quan sát

Container CPU riêng: 2 CPU, memory=1g, memory-swap=2g (tổng RAM+swap),
network=none, batch ảnh=1. Không gắn GPU, không dừng embedding cũ.
Model/runtime vẫn đọc từ E; output mới chỉ khoảng vài MB trên D, không build image
hoặc tải weight mới vào C.

| Thành phần, phiên mở rộng | Số đo |
| --- | --- |
| Nạp CLIP | 65,29 giây |
| Nạp QD / CG head | 4,96 / 3,03 giây |
| Decode mỗi video, median | 3,60 giây |
| CLIP ảnh mỗi video, median | 2,11 giây |
| Mã hóa query, median | 61,08 ms |
| QD head, median 100 cặp | 21,73 ms |
| CG head, median 100 cặp | 19,97 ms |
| Toàn tiến trình hai model, 20 video/100 query | 262,86 giây |
| Process RSS high-watermark | 1142,44 MiB |

RSS high-watermark của process gồm trang nhớ không đồng nhất với mức cgroup RAM
đang dùng; không coi 1142 MiB là số VRAM hoặc toàn bộ RAM hệ thống.
Container vẫn chịu giới hạn RAM/swap như trên. Head timing không gồm mã hóa query,
đọc đặc trưng, truy hồi hoặc HTTP. Không gọi ~20 ms là latency tìm kiếm end-to-end.

Baseline HTTP mở rộng có median 625,22 ms, min
334,76 ms, max 30,00 giây.
Phiên thu baseline và container CPU chạy chồng thời gian; đây là quan sát hành vi
với nhiều query khác nhau, không phải benchmark p95/cold/warm hay số đo ảnh hưởng
chạy đồng thời có kiểm soát. Nạp CLIP chậm hơn phiên pilot, không đủ dữ kiện để
quy hoàn toàn cho model hoặc suy ra tốc độ khi hệ thống rảnh.

## Xem lại dự đoán và artifact

Mở `data/temporal-search/group-b/reviewed-evaluation/checkpoint-review.html`
khi Docker/API cũ đang chạy. Chọn query, lọc validation/test hoặc cặp dương/âm,
bấm đoạn nhãn hoặc top-1 QD/CG để phát đúng timestamp rồi tự dừng.
Trang chỉ dùng để kiểm tra kết quả B6; không thay giao diện tìm kiếm ứng dụng.

Tất cả file gộp được tạo trong `data/temporal-search/group-b/reviewed-evaluation/`:

- `labels.jsonl`, `reference.jsonl`: 120 nhãn đã duyệt và nguồn gợi ý để audit.
- `baseline.jsonl`, `predictions.jsonl`: 120 response/240 predictions.
- `input-manifest.json`: hash từng đầu vào, cơ cấu dữ liệu và thời gian từng stage.
- `expansion-diagnostics.json`: đánh giá riêng 100 cặp mới.
- `combined-diagnostics.json`: đánh giá 120 cặp, chia validation/test.
- `stage-diagnostics.json`: lỗi lấy video và phân nhóm sự kiện ngắn/dài.
- `reviewed-label-analysis.json`, `reviewed-errors.csv`: thay đổi nhãn, score và lỗi từng câu.
- `checkpoint-review.html`: playback để đối chiếu nhãn và dự đoán.
- `playback-check.json`, `live-checks.json`: kiểm tra trình duyệt, 25 URL video
  hỗ trợ Range/HTTP 206 và trạng thái API/embedding/Qdrant sau phiên chạy.

Đã chạy 15 kiểm thử đánh giá, kiểm schema/contract và đối chiếu snapshot 341 file
luồng cũ: đều đạt, không đổi HEAD hoặc file cũ. API/embedding đều HTTP 200,
Qdrant vẫn có 16.569 point và container nghiên cứu đã tự thoát sau khi hoàn tất.

Tái tạo báo cáo từ artifact đã chạy, không nạp model hoặc gọi search:

```powershell
python temporal-search/evaluation/summarize_group_b.py
```

Công cụ kiểm human-verified, split/video identity, query cuối so với baseline/
predictions, đủ hai model và SHA nhãn được dùng trong phiên mở rộng.
Các query sửa trước inference được phép audit; query đổi sau khi có artifact
sẽ bị từ chối. File nguồn đã duyệt và kết quả pilot ban đầu được giữ nguyên.

## Quyết định kết thúc nhóm B và chuyển bước

B4 hoàn tất mục tiêu 100–200 cặp đã duyệt và baseline. B5 hoàn tất khảo sát và
chọn QD baseline kỹ thuật, CG đối chứng. B6 hoàn tất kiểm chứng CPU, tài nguyên,
timestamp và cơ sở quyết định; GPU chưa đo, chưa có train thực tế.

CG có 6/38 so với QD 4/38 đoạn validation đạt IoU 0,5, nhưng mean IoU gần nhau
và cả hai có nhiều lỗi. Giữ cả hai làm đối chứng, chưa chọn model thắng để phục vụ.
Điều kiện chấp nhận chất lượng chưa đạt không có nghĩa phần khảo sát còn chờ nhãn.

Bước tiếp theo chỉ nên là prototype giới hạn của C7–C8: đặc trưng theo timeline
và provider truy hồi video ứng viên độc lập, giữ nguyên quyền/bộ lọc bắt buộc và
luồng cũ. Đo target hit@5/10/20 trên validation trước khi đầu tư tích hợp C9/D.
Với video đúng mà grounding kém, kiểm đặc trưng, lưới 2 giây và model đối chứng;
không chỉ tăng cutoff hoặc tự kéo dài đoạn.

Chưa mở rộng cache toàn kho, triển khai endpoint/UI temporal hoặc train trong B.
Code train và checkpoint có sẵn, nhưng thời gian fine-tune trên máy này chưa đo.
E14 cần thử một phiên ngắn với loader/loss/optimizer/validation/checkpoint thực,
sau đó mới ước lượng thời gian. 120 cặp một người duyệt chưa chứng minh đủ cho
fine-tune có khả năng tổng quát; thiếu nhãn saliency phải được xử lý tường minh.
