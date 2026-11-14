# Temporal Search — Nhóm A

Ngày thực hiện theo múi giờ Asia/Saigon: 14/11/2026.

Đây là bộ thiết kế cho nhánh tìm kiếm temporal độc lập. Luồng cũ được giữ theo
working tree hiện tại, gồm cả những thay đổi chưa commit đã có trước nhiệm vụ này.
Nhánh temporal chưa có API chạy thật, model, Docker image hoặc giao diện.

## Sản phẩm của ba nhiệm vụ

| Nhiệm vụ | Sản phẩm | Trạng thái |
| --- | --- | --- |
| A1. Hiện trạng và phạm vi giữ nguyên | [LEGACY_BASELINE.md](LEGACY_BASELINE.md), công cụ chụp/đối chiếu và snapshot nguồn/live | Đã ghi nhận 341 file; đã bổ sung 3 response live, OpenAPI và kiểm tra media sau khi Docker được bật |
| A2. Kiến trúc độc lập | [ARCHITECTURE.md](ARCHITECTURE.md) | Đã chốt ranh giới, adapter, tài nguyên và cách triển khai dự kiến |
| A3. Hợp đồng dữ liệu | [API_CONTRACT.md](API_CONTRACT.md), [OpenAPI](../../temporal-search/contracts/openapi.json), [ví dụ](../../temporal-search/contracts/examples.json) | Đã đặc tả và có công cụ kiểm tra ví dụ |

## Cách kiểm tra

Chạy tại thư mục gốc repository bằng Python 3.9 trở lên.

```powershell
python temporal-search/tools/legacy_baseline.py verify --baseline data/temporal-search/group-a/baseline-20261114.json
python temporal-search/tools/validate_contract.py
```

Lệnh kiểm tra contract cần `jsonschema` trong Python đang dùng. Đây là công cụ
kiểm tra tài liệu, không thêm dependency vào backend cũ. Không import `app/`.

Snapshot máy này nằm trong `data/temporal-search/group-a/baseline-20261114.json`,
được `.gitignore` hiện có loại khỏi Git. Nó chứa SHA-256 và trạng thái công cụ,
không chứa nội dung `.env` hoặc credential.

Sau khi Docker được bật, snapshot live đã xác minh nằm ở
`data/temporal-search/group-a/baseline-live-verified-20261114.json`.
File này giữ nguyên ba response của `baseline-live-20261114.json` và bổ sung
trạng thái Docker được đọc với quyền truy cập named pipe. Kết quả media nằm ở
`media-check-20261114.json` cùng thư mục. Không ghi đè snapshot ban đầu.

Sau khi người dùng chạy stack cũ, chụp một snapshot mới bằng tên khác.

```powershell
python temporal-search/tools/legacy_baseline.py capture --output data/temporal-search/group-a/baseline-live.json --include-search
```

Công cụ không tự bật Docker hay stack, không tải model và không ghi vào database.
Các request search thông thường có thể làm backend tạo trace hoặc cache như khi
người dùng tìm kiếm. Ba query mẫu chỉ dùng để đối chiếu hành vi, không phải bộ
nhãn đánh giá chất lượng của nhiệm vụ B4. Chụp nhiều lần không thay thế phép đo
độ trễ có kiểm soát ở nhóm B/E.

## Phạm vi thay đổi

Toàn bộ sản phẩm nhóm A nằm dưới `docs/temporal-search/` và `temporal-search/`.
Dữ liệu chụp nằm dưới `data/temporal-search/`. Không sửa router, schema, search
engine, model, frontend, Compose, Makefile hay file cấu hình của luồng hiện tại.
Không khởi động lại service, reindex, migrate hoặc tạo tài khoản.

## Phần còn cần xác nhận

- Benchmark độ trễ có kiểm soát và suite backend đầy đủ; response runtime mẫu đã có.
- Khả năng nạp checkpoint và tài nguyên sử dụng, thuộc B5–B6.
- Media nào có thể dùng làm nguồn đặc trưng với timeline đầy đủ, thuộc B6/C7.
- Chất lượng/latency của nhánh mới và lợi ích fine-tune, thuộc E13–E14.

Hồ sơ này hoàn thành phần khảo sát nguồn, thiết kế và baseline live mẫu của nhóm A.
Ba response hợp schema và một cặp media hoạt động không thay thế bộ nhãn đánh giá
chất lượng hoặc suite backend đầy đủ.
