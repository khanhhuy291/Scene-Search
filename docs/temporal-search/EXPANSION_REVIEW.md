# Bộ mở rộng 100 yêu cầu gán nhãn

Đã nhận đủ `expansion.reviewed.jsonl`: 100 nhãn người dùng xác nhận, 79 dương/21 âm,
4 query tiếng Anh được sửa. Đã thu 100 response baseline và chạy mới 200 predictions
QD/CG trên query cuối. Kết quả cùng pilot (120 cặp) ở
[REVIEWED_EXPANSION_RESULTS.md](REVIEWED_EXPANSION_RESULTS.md).
Các phần dưới mô tả cách chuẩn bị và duyệt bộ nguồn; nhãn sơ bộ không thay thế
file nhãn người dùng đã xuất.

## Bộ hiện tại

Đã thay trực tiếp bộ query tại tên file cũ theo yêu cầu người dùng; không tạo
bản v2 hoặc bản sao bộ 100 cũ. Bộ pilot 20 nhãn đã duyệt được giữ riêng.

20 video vẫn giữ nguyên lựa chọn seed 20261114 từ các video ingest thành công,
không chọn theo thứ hạng search hoặc điểm model. Không trùng 5 video pilot hoặc
các prefix filename của chúng; mỗi video mới có prefix riêng. Prefix filename
không phải ID chuyến đi/camera đã được xác minh.

Query được viết sau khi xem contact sheet gồm 20 frame nguồn/video, khoảng
mỗi 2 giây từ giây 1 đến 39. Không dùng dự đoán model để đặt câu hỏi. Mỗi video
gồm 4 câu mô tả sự kiện quan sát được và 1 câu đối chứng: tổng 80 dương/20 âm
**sơ bộ**, 100 query tiếng Anh khác nhau kèm bản dịch Việt. Có 40 cặp validation
(8 video) và 60 cặp test (12 video).

- Requests: `data/temporal-search/group-b/expansion.requests.jsonl`.
- Trang duyệt: `data/temporal-search/group-b/expansion-review.html`.
- Frames và contact sheets: `data/temporal-search/group-b/expansion-review/`.
- Selection: `data/temporal-search/group-b/expansion-selection.json`.
- Nội dung quan sát để tái tạo: `temporal-search/evaluation/expansion-observations.json`.

Các nhãn ban đầu đều có `human_verified=false` và
`label_status=provisional_assistant_visual`. Khoảng thời gian là gợi ý từ các
frame thưa, chưa đảm bảo ranh giới chính xác hoặc đủ mọi lần xuất hiện. Có mốc
frame tham khảo bên dưới mỗi query. Các câu đối chứng chủ yếu phân biệt ngày/
đêm, tuyết và bối cảnh rõ ràng; chúng không đủ để đo năng lực với các câu âm khó.
Không dùng 100 nhãn này làm kết quả chất lượng chính thức trước khi người duyệt xác nhận.

## Duyệt theo từng phiên

```powershell
Start-Process "D:\DA\Scene-Search\data\temporal-search\group-b\expansion-review.html"
```

1. Đóng tab bộ cũ rồi mở lại trang ở đường dẫn trên. Không nạp bản nháp đã xuất
   từ bộ query cũ: query ID đã đổi để tránh ghép nhầm nội dung.
2. Điền tên người duyệt, xem đầy đủ video và đọc 5 query. Các lựa chọn có/không
   và khoảng giây đã điền sẵn chỉ là gợi ý; mọi ô xác nhận ban đầu đều bỏ trống.
3. Nếu câu mô tả đúng, giữ query; chỉnh thời gian bắt đầu/kết thúc và thêm mọi
   lần xuất hiện còn thiếu. Dùng `[[start,end]]` hoặc nhiều khoảng.
4. Nếu không có sự kiện sau khi xem hết video, chọn **Không có sự kiện trong video**
   và đặt thời gian `[]`. Không buộc phải sửa query thành câu dương. Nếu câu sai
   cách diễn đạt, có thể sửa tiếng Anh và tiếng Việt cùng nghĩa rồi gán nhãn lại.
5. Đánh dấu đã xem video và xác nhận từng nhãn sau khi kiểm tra. Sửa query hoặc
   thời gian sẽ bỏ xác nhận nhãn đó.
6. Bấm **Xuất JSONL** để lưu `expansion.reviewed.jsonl`. Có thể xuất giữa chừng;
   bản nháp giữ các chỉnh sửa nhưng chỉ nhãn được xác nhận mới là human-verified.
7. Phiên tiếp theo dùng **Nạp file đã xuất để tiếp tục** trên chính trang này.
   File phải khớp query IDs, video, duration và split; file bộ cũ bị từ chối.

Trang không tự lưu lên server. Lưu bản xuất trước khi đóng. Bộ pilot 20 nhãn
không cần duyệt lại. Khi hoàn tất, đặt file tại
`data/temporal-search/group-b/expansion.reviewed.jsonl`.

Tổng hai bộ sau khi duyệt sẽ là 120 cặp trên 25 video. Tỷ lệ 80/20 là thiết kế
ban đầu, có thể thay đổi sau khi kiểm tra thực tế; không ép nhãn theo tỷ lệ.
Các câu tương tự và nhiều query/video không phải những mẫu độc lập thống kê.
Việc người duyệt sửa query cần được ghi nhận trước khi đóng băng dữ liệu.

## Tái tạo bộ yêu cầu tại tên file hiện tại

Chỉ dùng `--replace` khi thực sự muốn thay bộ nguồn; trang duyệt không tự ghi
đè file nhãn người dùng đã xuất.

```powershell
python temporal-search/tools/build_expansion_requests.py --selection data/temporal-search/group-b/expansion-selection.json --videos data/temporal-search/group-b/expansion-review/videos.json --output data/temporal-search/group-b/expansion.requests.jsonl --replace
python temporal-search/tools/create_annotation_review.py --labels data/temporal-search/group-b/expansion.requests.jsonl --output data/temporal-search/group-b/expansion-review.html --review-dir expansion-review --export-name expansion.reviewed.jsonl
```

## Chạy baseline/model sau khi chốt query và nhãn

Đã chạy các bước dưới sau khi chốt nhãn. Collector có thể tiếp tục artifact
cùng query; runner từ chối RunName đã tồn tại. Muốn đo phiên mới, dùng tên output
và RunName khác, giữ nguyên artifact đã báo cáo.

```powershell
python temporal-search/tools/collect_pilot_baseline.py --queries data/temporal-search/group-b/expansion.reviewed.jsonl --output data/temporal-search/group-b/expansion-baseline.jsonl
.\temporal-search\run-checkpoint-pilot.ps1 -Queries data/temporal-search/group-b/expansion.reviewed.jsonl -RunName expansion-grounding-cpu
python temporal-search/evaluation/evaluate_pilot.py --labels data/temporal-search/group-b/expansion.reviewed.jsonl --reference-labels data/temporal-search/group-b/expansion.reviewed.jsonl --baseline data/temporal-search/group-b/expansion-baseline.jsonl --predictions data/temporal-search/group-b/expansion-grounding-cpu/predictions.jsonl --output data/temporal-search/group-b/expansion-diagnostics.json
```

Runner dùng CPU và container riêng. Không suy ra số đo GPU từ kết quả CPU.
Nếu query đổi sau khi thu artifact, chạy lại phần bị ảnh hưởng. Collector kiểm
nội dung query khi resume; predictions lưu query và SHA file đầu vào.

Gộp và chấm lại cả pilot/mở rộng từ artifact hiện có:

```powershell
python temporal-search/evaluation/summarize_group_b.py
```

Output ở `data/temporal-search/group-b/reviewed-evaluation/`, gồm JSON, CSV và
trang `checkpoint-review.html` để phát nhãn/đoạn dự đoán. Không cần chạy lại model
khi chỉ tái tạo báo cáo từ cùng đầu vào.
