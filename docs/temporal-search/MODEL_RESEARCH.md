# Khảo sát mô hình temporal grounding

Ngày khảo sát: 14/11/2026, Asia/Saigon. Source revision được ghi trong
[`source-lock.json`](../../temporal-search/research/source-lock.json).
Đây là đánh giá khả năng áp dụng, không phải bảng xếp hạng SOTA.

## Bài toán và QVHighlights

QVHighlights cung cấp query, các khoảng thời gian liên quan và saliency theo
clip. Mô hình grounding nhận video đã chọn và query, không thay thế bước tìm
video trong kho. Dashcam khác phân bố vlog/news nên cần thử trên dữ liệu riêng.
[Paper QVHighlights](https://arxiv.org/abs/2107.09609),
[định dạng annotation](https://github.com/jayleicn/moment_detr/blob/main/data/README.md).

Thử nghiệm dùng lưới 2 giây, CLIP ViT-B/32 512 chiều, thêm hai tọa độ temporal,
và token-level text features. Mỗi query có thể có nhiều moment. Frame đại diện
và scene đã chia sẵn chỉ giúp chọn ứng viên, không cung cấp supervision temporal.

## Đối chiếu năm mô hình

| Mô hình | Hướng chính | Train/fine-tune | Checkpoint và video riêng | Đánh giá áp dụng |
| --- | --- | --- | --- | --- |
| [Moment-DETR](https://github.com/jayleicn/moment_detr), [paper](https://arxiv.org/abs/2107.09609) | Dự đoán tập moment và saliency | `moment_detr/scripts/train.sh`, `pretrain.sh`, `--resume` | Có checkpoint và `run_on_video`; có bản CLIP-only | Baseline tham khảo. Dependency gốc Python 3.7/PyTorch 1.9 cần môi trường riêng |
| [QD-DETR](https://github.com/wjun0830/QD-DETR), [paper](https://arxiv.org/abs/2303.13874) | Cross-attention đưa query vào biểu diễn video, dùng negative pairs | `qd_detr/scripts/train.sh`, `pretrain.sh`, `--resume` | Checkpoint CLIP-only nằm trong repo tác giả; đã tải và chạy | Baseline tích hợp đầu tiên, 6.991.141 tham số phần grounding đã đo |
| [CG-DETR](https://github.com/wjun0830/CGDETR), [paper](https://arxiv.org/abs/2311.08835) | Hiệu chỉnh tương quan clip–word, dummy tokens và moment-aware saliency | `cg_detr/scripts/train.sh`; có cấu hình resume/pretraining | CLIP-only qua Git LFS; đã tải và chạy | Model đối chứng, 12.021.035 tham số grounding đã đo |
| [UniVTG](https://github.com/showlab/UniVTG), [paper](https://arxiv.org/abs/2307.16715) | Thống nhất nhãn interval/point/saliency, pretraining quy mô lớn | `scripts/pretrain.sh`, `qvhl_pretrain.sh`, `--resume`; cần thích nghi script Slurm | Model zoo có CLIP-only pretrained và multi-dataset fine-tuned | Phương án nghiên cứu tiếp. Chưa tải/nạp checkpoint trong lần này |
| [FlashVTG](https://github.com/Zhuo-Cao/FlashVTG), [paper](https://arxiv.org/abs/2412.13441) | Feature layering và adaptive score handling | `FlashVTG/scripts/train_qv_slowclip.sh`, cấu hình InternVideo2 riêng | Model zoo SlowFast+CLIP/InternVideo2 kèm log | Chưa chạy; cần encoder/feature tương ứng, không đổi trực tiếp từ cache CLIP-only |

Thông tin model zoo UniVTG được kiểm tra tại
[model.md](https://github.com/showlab/UniVTG/blob/main/model.md).
FlashVTG có nhiều backbone, không coi mọi cấu hình đều yêu cầu InternVideo2.
Không suy ra model nhanh trên máy này từ tên gọi hoặc điểm benchmark của tác giả.

## Checkpoint thực sự dùng

Đã tải CLIP khoảng 354 MB, QD-DETR khoảng 84 MB và CG-DETR khoảng 143 MB.
Các file lưu riêng dưới `E:\SceneSearchData\temporal-search\models`.
SHA-256 và nguồn tải được khóa trong source lock. CLIP kiểm SHA công bố, QD kiểm
Git blob hash ở commit cụ thể, CG kiểm SHA-256 trong Git LFS pointer của tác giả.

QD: `run_on_video/qd_detr_ckpt/model_best.ckpt`, commit
`f8628f79f7c651b586300b142dbe9b85e43857cc`, epoch trong checkpoint là 84.
CG: `run_on_video/CLIP_ckpt/qvhighlights_onlyCLIP/model_best.ckpt`, commit
`212b2e49a0893512930d63b9294a8c066347e606`, epoch là 134.

Các URL Zenodo tải trực tiếp trả 403 trong môi trường này. Endpoint API của
Zenodo tải chậm nhưng cuối cùng cũng hoàn tất hai weight Lighthouse; các file
đó được giữ như tài liệu thử nghiệm, không phải weight dùng cho kết quả pilot.
Không đổi qua checkpoint ngẫu nhiên từ nguồn không xác định.
[Model zoo Lighthouse](https://zenodo.org/records/13960580).

## Những khác biệt code đã kiểm tra

- Head được import từ Lighthouse đã pin; state dict của cả hai checkpoint tác giả
  nạp strict thành công, không bỏ key hoặc nạp weight ngẫu nhiên để che mismatch.
- Checkpoint gốc lưu `a_feat_dim=None`. Adapter video-only chuyển giá trị đó
  thành 0 trước khi dựng head; không sửa trọng số hoặc code backend cũ.
- Training loader và demo của tác giả L2-normalize video/text features trước
  TEF. Một hàm predictor của Lighthouse ở revision đã đọc tính normalized
  features nhưng concat tensor gốc. Runner dùng hành vi của demo tác giả, không
  sao chép lỗi này.
- Video raw có display matrix xoay ±90 độ. Runner áp hướng hiển thị trước khi
  xác định scale/crop, rồi dùng FFmpeg fps=0.5. Không resize theo kích thước coded
  portrait rồi ép video landscape thành ảnh méo.
- Dùng một CLIP encoder chung cho ảnh và token để giảm bộ nhớ. Đã kiểm tra token
  EOT sau projection khớp `encode_text` chính thức, sai số lớn nhất bằng 0 trong
  hai câu kiểm tra. Đây là sanity check đặc trưng, không chứng minh chất lượng.

Đối chiếu source tác giả:
[QD run](https://github.com/wjun0830/QD-DETR/blob/f8628f79f7c651b586300b142dbe9b85e43857cc/run_on_video/run.py),
[QD data utils](https://github.com/wjun0830/QD-DETR/blob/f8628f79f7c651b586300b142dbe9b85e43857cc/run_on_video/data_utils.py),
[CG run](https://github.com/wjun0830/CGDETR/blob/212b2e49a0893512930d63b9294a8c066347e606/run_on_video/run.py).

## Khả năng train và tốc độ

Các repo đều có code train. Với dự án này, hướng khả thi cần thử là đóng băng
encoder và fine-tune head bằng đặc trưng trích xuất sẵn. Cần nhãn query–window;
MOT hiện có không tự cung cấp đầy đủ nhãn cho query tự do. Nếu dùng loss saliency
phải có nhãn phù hợp hoặc điều chỉnh loss một cách tường minh.

Moment-DETR công bố 200 epoch trong khoảng 4 giờ trên RTX 2080 Ti khi đã có
features. Đó là số tác giả, không phải thời gian GTX 1650 hoặc phép đo ở đây.
[Thông tin training](https://github.com/jayleicn/moment_detr#training).

Chưa chạy fine-tune trong nhóm B, chưa đo thời gian một epoch trên dashcam.
Một artifact benchmark head với dữ liệu giả đã có từ bước nghiên cứu trước,
nhưng không dùng nó làm ước lượng phiên train thật. E14 cần đo loader, loss,
optimizer, validation và checkpoint trên dữ liệu đã duyệt trước khi dự báo.
Không tái tạo pretraining hàng triệu nhãn của UniVTG trên laptop này.

## Quyết định sau thử nghiệm

Giữ QD-DETR làm baseline kỹ thuật và CG-DETR làm đối chứng. Đã chạy CPU và chấm
120 cặp được duyệt, nhưng chưa đủ bằng chứng chọn model phục vụ. Trên validation
gộp, CG đạt IoU≥0,5 ở 6/38, QD ở 4/38; mean IoU gần nhau. Hai model vẫn có vấn
đề với đoạn dài/query âm và cần kiểm tra truy hồi ứng viên riêng. Không chọn
hyperparameter trên test, chưa train hoặc triển khai checkpoint nguyên bản.
Kết quả mới ở [REVIEWED_EXPANSION_RESULTS.md](REVIEWED_EXPANSION_RESULTS.md).
