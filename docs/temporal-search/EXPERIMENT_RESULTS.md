# Kết quả thử checkpoint trên dashcam

Cập nhật mới nhất: đã hoàn tất 120 nhãn, 120 baseline và 240 predictions tại
[REVIEWED_EXPANSION_RESULTS.md](REVIEWED_EXPANSION_RESULTS.md). Các số dưới đây
chỉ là phiên pilot 5 video ban đầu.

Cập nhật: đã nhận đủ 20 nhãn người dùng xác nhận và chấm lại tại
[REVIEWED_PILOT_RESULTS.md](REVIEWED_PILOT_RESULTS.md). Các bảng diagnostics
sơ bộ dưới đây được giữ làm lịch sử của phiên chạy trước khi duyệt, không phải
kết quả mới nhất. Thời gian chạy model không thay đổi do chỉ chấm lại nhãn.

Ngày chạy: 14/11/2026, Asia/Saigon. Báo cáo là nghiên cứu khả thi, chưa xác nhận
chất lượng production. Dữ liệu thô nằm dưới `data/temporal-search/group-b/` và
được Git ignore. Model/runtime riêng ở E, không cài vào service cũ.

## Môi trường và tính tương thích

- Máy có RAM vật lý khoảng 7,83 GiB; GTX 1650 Max-Q 4096 MiB đang phục vụ
  embedding cũ. Không dừng hoặc đổi cấu hình embedding.
- Dùng container CPU riêng, 2 CPU, memory=1g, memory-swap=2g, network=none,
  batch ảnh=1. Giới hạn RAM/swap và I/O bind mount ảnh hưởng số đo.
- Tái sử dụng image immutable sẵn có, Python 3.11, Torch 2.15.0+cu132; chạy
  `device=cpu`. Ba dependency phụ cài vào runtime directory riêng trên E.
- GPU experiment bị automatic approval review từ chối vì nguy cơ OOM khi chạy
  đồng thời với embedding cũ. Không thử lại GPU bằng đường khác. Không có số đo
  GPU cho pipeline CLIP+grounding trong báo cáo này.
- QD/CG checkpoint từ repo tác giả nạp strict thành công; không bỏ key.
  EOT/token sanity check với CLIP chuẩn có max absolute error=0 ở hai câu thử.

## Khối lượng chạy thực tế

5 video raw khoảng 40 giây/video, tổng 100 clip CLIP lấy mẫu 2 giây. Có 20 query
và 40 lần grounding theo hai model. Video đều có display rotation ±90 độ, đã
xử lý trước scale/crop. 20 clip biểu diễn 40 giây, trong khi video thực dài hơn
khoảng 0,16–0,37 giây; không khẳng định phần đuôi chưa lấy mẫu đã được nhìn thấy.

Các file kết quả:

- `legacy-baseline.jsonl`: 20 request API cũ, limit=20, giữ default mode/agentic/rerank.
- `grounding-cpu/predictions.jsonl`: 20 dự đoán/model và saliency.
- `grounding-cpu/summary.json`: tài nguyên, model load và thời gian từng stage.
- `pilot-diagnostics.json`: so sánh có nhãn sơ bộ, chia validation/test.
- `clip-token-sanity.json`: kiểm tra token features.
- `annotation-review.html`: trang để người dùng xác nhận nhãn độc lập.

## Số đo CPU

| Thành phần | Kết quả quan sát |
| --- | --- |
| Nạp CLIP | 10,12 giây |
| Nạp QD-DETR head | 5,15 giây |
| Nạp CG-DETR head | 2,16 giây |
| Giải mã/lấy mẫu mỗi video | 3,20–3,82 giây |
| CLIP ảnh mỗi video, 20 frame | 1,91–2,48 giây |
| Mã hóa query, median 20 câu | 240,32 ms |
| QD head, median 20 cặp | 23,32 ms/cặp |
| CG head, median 20 cặp | 20,76 ms/cặp |
| Toàn bộ tiến trình hai model | 78,35 giây |
| Process RSS high-watermark theo getrusage | 1130,36 MiB |

Head timing đo khi feature đã ở bộ nhớ, không gồm query encoding, đọc cache,
retrieval hay HTTP. Không gọi 23 ms là thời gian trả một query end-to-end.
Chênh vài ms giữa hai head chưa đủ kết luận model nào nhanh hơn nói chung.
RSS high-watermark là số của process, không phải bộ nhớ GPU hoặc mức RAM độc
quyền của cả hệ thống. Chưa benchmark CPU toàn pipeline bằng nhiều lần lặp.

API cũ trả HTTP 200 cho cả 20 query. Query đầu khoảng 17,69 giây, các query còn
lại khoảng 0,004–0,787 giây; không suy ra p95 cold/warm từ bộ câu khác nhau.
Trong lúc thu baseline có phép kiểm tra load head CPU độc lập, nên đây là
baseline hành vi, không phải benchmark latency hệ thống rảnh.

## Diagnostics chất lượng — chỉ nhãn sơ bộ

Chưa có record human-verified. Không dùng bảng này để công bố mô hình tốt hơn.

| Split | Cặp dương/âm | Target video được API cũ trả trong top 20 | QD mean IoU khi cho sẵn target | CG mean IoU khi cho sẵn target |
| --- | --- | --- | --- | --- |
| Validation, 2 video | 6 / 2 | 3/6 | 0,325 | 0,286 |
| Test, 3 video | 9 / 3 | 1/9 | 0,289 | 0,267 |

Hai cột IoU là bài toán đã cho video đúng, còn cột target hit phải tìm video
trong kho. Không so trực tiếp để suy ra mức cải thiện end-to-end. Trên test,
R@1 IoU>=0.5 sơ bộ là QD 1/9 và CG 3/9, nhưng mẫu nhỏ/chưa duyệt và không dùng
để chọn hyperparameter hoặc tuyên bố model thắng.

QD thường dự đoán gần toàn bộ video, làm mất độ chính xác với sự kiện ngắn.
CG có một số đoạn ngắn hơn nhưng vẫn sai thời điểm. QD có điểm top-1>0.5 ở cả
5 cặp âm; CG có ở 4/5 cặp. Ví dụ query lớp học hoặc ánh sáng ban ngày với video
đêm vẫn có thể nhận điểm cao. Đây là dấu hiệu cần hiệu chỉnh/từ chối, không phải
xác suất model đúng và cũng không phải false-positive rate toàn corpus.

Một số query về night/bus/people/parking bị API cũ loại do concept chưa xác nhận
hoặc similarity floor. Vì vậy grounding không thể cứu video đã mất ở bước ứng
viên. C8 cần thử provider riêng có kiểm soát recall, không sửa luồng cũ hoặc bỏ
quyền truy cập để tăng số kết quả.

## Kết luận kỹ thuật và gate tiếp theo

Checkpoint CLIP-only chạy được trên video dự án bằng CPU mà không cần train.
Chi phí chính trong phép chạy này là đọc video, CLIP và startup. Có lý do xây
cache theo thời gian, nhưng cache production của C7 chưa được triển khai.

Tại phiên chạy ban đầu, chưa đạt gate khẳng định chất lượng cải thiện và B4 còn
chờ nhãn. Nay pilot đã được duyệt, kết quả mới ở báo cáo liên kết đầu trang.
B5 đã có khảo sát/nguồn khóa; B6 có prototype CPU, GPU chưa đo. Không train hoặc
triển khai model phục vụ trong nhóm B.

Sau khi nhãn được duyệt, ưu tiên đánh giá lại, kiểm tra recall bước ứng viên và
negative rejection trước khi cân nhắc fine-tune. Ngưỡng/encoder/model tiếp theo
chỉ chọn bằng validation. Luồng hiện tại tiếp tục là luồng phục vụ.
