# Chạy lại thí nghiệm checkpoint

Luồng cũ không bị sửa. Các bước này dùng container tạm và thư mục riêng. Không
chạy lệnh train, không thêm service vào Compose cũ và không cung cấp GPU cho
container thí nghiệm.

## Trạng thái máy đã chuẩn bị

- `data/research/lighthouse` ở commit `9b04316efe436d0cd4082e565e22b75f5f8bdb98`.
- `data/research/openai-clip` ở commit `d05afc436d78f1c48dc0dbf8e5980a9d471f35f6`.
- Các weight và runtime ngoài Git nằm ở `E:\SceneSearchData\temporal-search`.
- Base image ID và package bổ sung được khóa trong
  [`source-lock.json`](../../temporal-search/research/source-lock.json).
- Nhãn sơ bộ và script trong `temporal-search/`, không phụ thuộc import backend.

Chạy từ gốc repository:

```powershell
.\temporal-search\run-checkpoint-pilot.ps1
```

Script tạo output mới có hậu tố ngẫu nhiên, kiểm revision/image và từ chối ghi
đè output cũ. Nó chạy lại CPU 5 video và 40 lần grounding, không tạo server.
Giới hạn 1g RAM, memory-swap=2g là tổng RAM+swap theo Docker, không phải 2g
swap cộng thêm. Tránh chạy nhiều phiên nghiên cứu cùng lúc trên máy 8 GB RAM.

## Nếu cần chuẩn bị lại weight/runtime

Giữ source ở đúng revision trong lock và kiểm dung lượng trước. Không cài toàn
bộ dependency Lighthouse vào `app/` vì setup upstream có ràng buộc NumPy và
Transformers khác môi trường hiện tại.

```powershell
python temporal-search/tools/download_research_models.py --model-dir E:\SceneSearchData\temporal-search\models
```

Download tool kiểm hash công bố/Git blob và lưu manifest. Chỉ load checkpoint
từ bộ nguồn đã kiểm đó. CLIP và hai head tổng khoảng 581 MB theo byte file,
chưa tính runtime. Hai bản Lighthouse tải thêm trong phiên nghiên cứu không
được runner dùng và không bắt buộc cho lần chạy lại.

Dependency bổ sung là `easydict==1.13`, `einops==0.8.1` và
`imageio-ffmpeg==0.6.0`. Chúng được cài vào `/runtime` bind mount E bằng container
tạm, không ghi vào layer hoặc package của service cũ. Danh sách ở
[`requirements-linux-extra.txt`](../../temporal-search/research/requirements-linux-extra.txt).

## Chạy lại baseline và diagnostics

Baseline collector lưu từng query và resume theo query_id. Muốn đo một phiên
mới phải dùng tên output mới. Nó không đổi default search/rerank/agentic.

```powershell
python temporal-search/tools/collect_pilot_baseline.py --queries temporal-search/evaluation/pilot.provisional.jsonl --output data/temporal-search/group-b/legacy-baseline-rerun.jsonl
python temporal-search/tools/create_annotation_review.py --labels temporal-search/evaluation/pilot.provisional.jsonl --output data/temporal-search/group-b/annotation-review.html
python temporal-search/evaluation/evaluate_pilot.py --labels temporal-search/evaluation/pilot.provisional.jsonl --baseline data/temporal-search/group-b/legacy-baseline.jsonl --predictions data/temporal-search/group-b/grounding-cpu/predictions.jsonl --output data/temporal-search/group-b/pilot-diagnostics.json --allow-provisional
```

Diagnostics với nhãn người duyệt và cách xuất nhãn nằm ở
[EVALUATION_PILOT.md](EVALUATION_PILOT.md). Kết quả dự đoán không thay thế nhãn.

## Tái tạo báo cáo sau khi có đủ 120 nhãn

Hai phiên CPU đã hoàn tất. Có thể gộp nhãn, kiểm hash/query identity, chấm lại
và dựng trang playback mà không gọi search hoặc nạp model:

```powershell
python temporal-search/evaluation/summarize_group_b.py
```

Output tại `data/temporal-search/group-b/reviewed-evaluation/`. Công cụ yêu cầu
đủ 120 baseline, 240 predictions, hai checkpoint và SHA nhãn mở rộng khớp đúng
phiên chạy. Nó giữ riêng file nhãn người dùng và kết quả pilot trước đây.
Nếu input khác manifest cũ, dừng để người dùng kiểm tra thay vì ghi đè báo cáo
theo một bộ đầu vào khác. Chi tiết ở
[REVIEWED_EXPANSION_RESULTS.md](REVIEWED_EXPANSION_RESULTS.md).

## Kiểm tra hồi quy

```powershell
python -m unittest discover -s temporal-search/evaluation -p "test_*.py" -v
python temporal-search/tools/validate_contract.py
python temporal-search/tools/legacy_baseline.py verify --baseline data/temporal-search/group-b/source-before.json
```

Nếu HEAD thay đổi vì người dùng commit sau baseline, verifier báo điều đó ngay
cả khi source cũ không đổi. Không xóa baseline để che cảnh báo; phân biệt HEAD
thay đổi với file legacy bị sửa. Không commit weight, video, cache hoặc snapshot.
