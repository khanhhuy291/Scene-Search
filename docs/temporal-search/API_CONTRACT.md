# A3 — Hợp đồng API temporal 0.1.0

Đặc tả ở [openapi.json](../../temporal-search/contracts/openapi.json).
Ví dụ ở [examples.json](../../temporal-search/contracts/examples.json).
Tất cả ID, điểm, model và thời gian trong ví dụ là giả để minh họa contract.
Không có endpoint temporal đang chạy, không có kết quả đo model trong nhóm A.

## Endpoint và phạm vi

- `GET http://127.0.0.1:8002/health`: 200 khi upstream và grounder ready, 503 nếu
  chưa ready. Health không được kích hoạt download/model load hoặc extraction.
- `POST http://127.0.0.1:8002/api/v1/temporal-search`: request sync có budget tổng
  ở server, chỉ xử lý tối đa số video ứng viên đã chọn. Không dùng 202/job trong v1.
- API cũ `POST :8000/api/v1/search`, schema, router và UI cũ giữ nguyên.
- Không nhận model path, storage key, địa chỉ upstream hoặc local file từ caller.

## Request

| Trường | Mặc định/giới hạn | Ý nghĩa |
| --- | --- | --- |
| `query` | Bắt buộc, trim, 1–1000 ký tự | Query gốc gửi tới nhánh truy hồi cũ |
| `query_language` | `auto`, hoặc `en`, `vi` | Gợi ý ngôn ngữ cho QueryAdapter |
| `grounding_query` | null hoặc 1–1000 ký tự | Câu tiếng Anh caller đã kiểm tra, chỉ dùng cho grounding |
| `candidate_video_count` | 10, từ 1–20 | K video khác nhau tối đa được đưa vào grounding |
| `moments_per_video` | 3, từ 1–5 | Số đoạn tối đa của một video |
| `limit` | 10, từ 1–20 | Số video trả tối đa, phải <= K sau khi áp default |
| `filters` | `{}` | Bản độc lập của các trường lọc hiện tại, chuyển tiếp đúng ý nghĩa |

Filters hỗ trợ `dataset`, `video_ids`, `weather`, `timeofday`, `scene`,
`objects_any`, `objects_all`, `min_object_counts`, `behaviors`, `time_range_s`.
Mảng rỗng/null tương đương không có điều kiện, không biến thành deny-all.
Không bỏ qua trường không hỗ trợ, request phải trả 422. Điều kiện user chọn
được giữ nguyên, điều kiện tự suy ra upstream phải được ghi nhận trong trace
nội bộ cho đánh giá. Không đưa fallback metadata của index thành nhãn chuẩn.

`time_range_s` gồm hai số hữu hạn, `0 <= start < end`. Nhánh mới dùng khoảng đó
để giới hạn đoạn kết quả, không chỉ dùng như filter chọn video. Window trích xuất
vẫn có thể có ngữ cảnh ngoài khoảng đó; output phải nằm trong khoảng yêu cầu.

Nếu query cần dịch nhưng chưa cấu hình translator và không có `grounding_query`
phù hợp, trả 422 `grounding_query_required`. Không chuyển câu Việt thẳng vào
CLIP rồi báo như đã xử lý đúng. Việc nhận diện `auto` cần kiểm chứng ở B6; khi
không chắc thì yêu cầu grounding query, không giả định một câu là tiếng Anh chỉ
vì không có dấu. Không tự cắt query dài quá tokenizer; trả 422 hoặc yêu cầu câu
ngắn hơn. Hai giới hạn độ dài ký tự và token là độc lập.

## Response và điểm số

`query.original`, `retrieval_text`, `grounding_text`, `translation_source` giúp
đánh giá đúng nguồn sai lệch. Translation không thay query gửi API cũ.

`results` là video duy nhất, mỗi video có scene evidence và các moment mới.
`moment_id` là ID query-dependent, không phải Qdrant point ID. Không ghi predicted
moment vào collection cũ. Caption của scene evidence không được tự sao chép làm
mô tả cho đoạn dự đoán mới; v1 không có trường caption khẳng định nội dung đoạn.

`retrieval_score` và `grounding_score` giữ điểm gốc, không cộng trực tiếp và không
hiển thị thành phần trăm chính xác. Thứ hạng video ban đầu theo retrieval,
thứ hạng moment theo model/postprocessor, tie-break xác định bằng ID/thời gian.
Nếu thay chính sách ở E13 phải tăng phiên bản/cấu hình được ghi trong evaluation.

`scope=candidate_videos_only` luôn bắt buộc. `upstream_exhaustive=true` không
có nghĩa tất cả video trong kho đã được grounding.

| Trường retrieval/counts | Quy tắc |
| --- | --- |
| `provider=legacy-api` | `scene_count_scope=returned_matched_moments`, `raw_ann_count=null` |
| `provider=qdrant-readonly` | Chỉ khi đã triển khai/đánh giá C8; raw count là pool sau filter của truy vấn Qdrant, trước lọc semantic/gom video của nhánh mới |
| `candidate_scenes_observed` | Số scene ID duy nhất provider thực sự thu được, không dùng `total_keyframes` thay số này |
| `candidate_videos_received` | Số video duy nhất đã chọn, <= K |
| `candidate_videos_processed` | Số video grounding hoàn thành, kể cả không có moment vượt tiêu chí |
| `candidate_videos_skipped` | Cache/model/budget/timeline khiến video không hoàn thành |
| `returned_videos` | Bằng `len(results)`, <= limit và <= processed |

`processed + skipped = received`. Scene/moment ID không trùng trong phạm vi
response. Evidence là tập con quan sát được, không giả định là mọi scene liên
quan. `truncated` cho biết provider đã dừng vì budget còn cursor/pool chưa đọc.

## Timestamp và playback

Moment/evidence dùng giây trên timeline video nguồn, đoạn `[start,end)`.
Tất cả số hữu hạn, `0 <= start < end <= video_duration_s`.
Đầu/cuối hiển thị có thể format làm tròn, giá trị seek giữ độ chính xác thực.

`playback` có `url`, `kind`, `origin_s`, `duration_s`, `privacy_state`.

- `kind=full_video` thì `origin_s=0`; cần kiểm chứng duration/timeline thực.
- `kind=subclip` thì player seek tại `moment.start-origin_s` và dừng tại
  `moment.end-origin_s`. URL phải bao phủ mọi moment trong video result đó,
  nếu không v1 trả `unavailable` thay vì một URL sai cho các moment khác.
- `kind=unavailable` thì URL null, origin/duration bằng 0. Không làm mất kết quả
  semantic chỉ vì chưa tạo media, UI phải biết video chưa phát được.
- URL tương đối upstream resolve theo API cũ trước khi đưa sang origin mới.
  Có thể dùng proxy riêng hoặc absolute loopback URL, không để browser gọi nhầm
  `:8002/api/v1/media/clip/<point-id>` như đã có route đó.
- Media không chứa storage key, presigned credential hay token trong URL.
  Bearer/cookie theo caller; không retry anonymous khi đã bị 401/403.

Generator hiện giữ hình nguồn nên phải ghi `source_preserving` khi đã xác nhận.
`anonymized_verified` chỉ dùng khi có bằng chứng cho asset cụ thể. Thiếu thông
tin là `unknown`, không suy ra từ bucket tên derived. Thumbnail moment phải
nằm trong đoạn, không lấy ảnh scene cũ nếu không kiểm tra được timestamp.

## Trạng thái và lỗi

| HTTP/status | Quy tắc |
| --- | --- |
| 200 `complete` | Xử lý xong mọi video nhận được, không mất stage, có ít nhất một video kết quả; không phải chứng nhận đáp án đúng |
| 200 `no_match` | Không có ứng viên hoặc không có moment qua tiêu chí, mọi bước cần thiết đã hoàn thành, không lỗi bị che |
| 200 `partial` | Có upstream degraded/truncated hoặc video bị skip, ít nhất có phần xử lý hợp lệ; có warnings, có thể results rỗng |
| 401/403 | Giữ ý nghĩa từ chối caller của upstream; không nới phạm vi hoặc giả thành no_match |
| 422 | Request/query không hợp lệ, limit>K, range sai, trường lạ hoặc thiếu grounding query |
| 503 | Model/upstream không sẵn sàng hoặc không xử lý được video ứng viên nào do thiếu cache/lỗi |
| 504 | Hết deadline mà chưa có phần xử lý có ích để trả partial |

Nếu hết budget sau khi xử lý được một phần thì trả partial và lý do, không
tuyên bố complete. Không dùng legacy fallback trong 200 của v1; UI có thể cho
người dùng chạy luồng cũ riêng. Không extraction/train ngầm trong request.

`timings_ms` có total và từng stage, dùng đồng hồ monotonic, không phải SLA.
`model` ghi model/checkpoint/feature version thực đã dùng, không ghi model chỉ
được cấu hình nhưng chưa nạp. Response lỗi không giả tạo kết quả grounding.

## Cách xác minh và giới hạn

`validate_contract.py` kiểm tra JSON Schema 2020-12 cho các schema và ví dụ,
internal refs, default/cross-field/timestamp/counts và một số ví dụ cố ý sai.
Đây không phải trình kiểm định đầy đủ mọi quy tắc OpenAPI hay test server.

Lệnh kiểm tra không import backend hoặc gọi mạng. Khả năng nạp checkpoint,
phát media đúng, auth runtime, chất lượng semantic và tốc độ phải được kiểm
chứng riêng ở B6/D11/E13. Định dạng theo
[OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0).
