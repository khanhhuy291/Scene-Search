# Kế hoạch nâng cấp scene ingestion và dữ liệu phục vụ search

Ngày lập: 22/11/2026. Phạm vi đối chiếu: mã nguồn trong `code/Scene-Search` tại workspace hiện tại.

> Cập nhật phạm vi ngày 25/11/2026 theo quyết định mới của người dùng: chỉ dùng một pipeline, cố định `content_time` + `medoid`, bỏ fingerprint/snapshot cả trong database, payload và Celery, cùng metadata chẩn đoán phương pháp/pooling/ranh giới. Giữ dữ liệu frame/thời điểm đại diện, thumbnail, evidence theo frame và các kiểm tra trước khi ghi. Video đã indexed được bỏ qua; reprocess chủ động dùng `force=true`. Migration mới nhất trong code chỉ giữ 3 cột đại diện/thumbnail. PostgreSQL local đã được đồng bộ bằng transaction gỡ đúng 8 cột dư thừa, không thay đổi revision `20261122_0009`, không xóa bản ghi; sau kiểm tra đã dừng lại PostgreSQL, chưa khởi động API/worker. Các mô tả về fingerprint, snapshot, mode time/middle và kết quả kiểm tra ở các pha bên dưới là lịch sử triển khai, không phải yêu cầu hiện hành. Các version/model field đã tồn tại trước commit `f8ff174` vẫn được giữ.

Trạng thái: **Đang triển khai từng pha; chưa nghiệm thu toàn bộ**. Bốn quyết định D1–D4 và các xác nhận bổ sung bên dưới đã được người dùng đồng ý trong chat. Phạm vi hiệu lực mới nhất ở mục 1.6: dùng ngưỡng content-aware thử nghiệm có chú thích, bỏ quality filter và evaluator, ingest lại từ dữ liệu local đã reset. Không coi ngưỡng thử nghiệm là kết quả calibration/benchmark.

## 1. Mục tiêu, quyết định đã chốt và giới hạn

### 1.1. Quyết định đã được người dùng xác nhận

| ID | Quyết định | Hệ quả triển khai |
| --- | --- | --- |
| D1 | Qwen chỉ encode frame sau dedup; SigLIP tổng hợp toàn bộ sample hợp lệ của scene | Tách rõ tập frame pooling của hai model; không tăng Qwen lên mọi sample |
| D2 | VLM phân tích tối đa 3 frame khác nhau/scene, có cấu hình | Candidate gồm frame đại diện và frame khác biệt; giữ timestamp và provenance; không mặc định luôn gọi đủ 3 lần |
| D3 | Scene tối đa 5 giây ở bản đầu, có thể cắt sớm theo nội dung | 5 giây là giới hạn thật trên `[start, end)`, không chỉ khoảng cách timestamp keyframe; 8 giây nằm ngoài rollout đầu |
| D4 | Cho phép sửa adapter/filter/API phía search; giữ thuật toán ranking | Đồng bộ schema, polarity, timestamp và bằng chứng đồng thời; giữ các tower, ANN, RRF và gom kết quả theo video |

### 1.2. Hợp đồng cần giữ

- Một **point Qdrant/scene**, với hai named vector: `qwen` 2048 chiều và `siglip` 768 chiều ở cấu hình production hiện tại. Không gọi nhầm đây là một vector vật lý.
- Một thumbnail đã anonymize/scene, chọn cố định lúc ingestion; không chọn lại theo search text.
- Full-video anonymized playback vẫn dùng chung cho các scene; không encode thêm một MP4 riêng cho mỗi scene.
- Query text vẫn encode bằng đúng tower tương ứng; chuẩn hóa L2 ở biên encoder cho cả ảnh và text.
- `granularity="segment"` cho dữ liệu mới của pipeline chính. Luồng offline đang ghi `frame` phải tiếp tục đọc được bằng adapter legacy.
- Không thay sampling FPS của môi trường một cách ngầm định: code default hiện 1 fps, `.env.example` hiện 5 fps. Mỗi run ghi giá trị thực đã resolve.
- Giữ privacy verification trước các bước inference downstream; thumbnail và ảnh gửi VLM phải là `display_image` đã verified.
- Embedding hiện dùng `frame.image` gốc; thay đổi đầu vào embedding sang ảnh blur là một thí nghiệm riêng, không đưa lẫn vào bản nâng cấp này.

### 1.3. Ngoài phạm vi

Không huấn luyện model mới, không triển khai behavior detector/tracker mới, không tạo query-dependent thumbnail, không lưu từng frame thành point trong pipeline chính, không thay agentic/HyDE/RRF hoặc thiết kế lại giao diện. Không tự chạy reindex toàn bộ dữ liệu hay chuyển collection live trong giai đoạn lập kế hoạch.

### 1.4. Xác nhận bổ sung trước triển khai (22/11/2026)

Người dùng đã đồng ý làm theo sáu đề nghị sau sau vòng đối chiếu code:

1. Đưa riêng điều phối Scene Builder trước Dedup và reset dedup theo scene lên P0-A để nghiệm thu giới hạn 5 giây. Streaming/bộ nhớ và thay đổi pooling vẫn ở P1-A.
2. Dùng chung chính sách timestamp hiện có của playback cho decode/encode: giữ PTS nguồn khác zero, sửa timestamp trùng/lùi tăng tối thiểu 1 ms; không reset timeline về zero.
3. Quyết định bàn giao ban đầu: triển khai và kiểm chứng đến P1-B trước; chờ dữ liệu calibration/holdout phù hợp để nghiệm thu P1-C trở đi. Phạm vi tiếp tục đã được người dùng cập nhật tại mục 1.5; không tự gán threshold.
4. Schema scene mới dùng một nhóm AND cùng observation cho required/object/count cần đồng thời; không thêm temporal parser, giữ legacy.
5. Quality dùng phương sai Laplacian qua Pillow và tỷ lệ clipping với ngưỡng chờ calibration; VLM farthest-point theo min-distance đến tập đã chọn, thời gian làm tie-break; caption ghép mô tả có timestamp, không thêm LLM call.
6. Rollout dự kiến canary tách biệt rồi batch nhỏ có snapshot/rollback, chấp nhận từng video tạm mất khỏi search khi thay dữ liệu. Xác nhận thiết kế không đồng nghĩa cho phép tự chạy reindex/xóa dữ liệu thật.

### 1.5. Xác nhận tiếp tục P1-C/P1-D: kiểm thử chức năng trước, đánh giá sau

Người dùng cho phép triển khai và kiểm thử chức năng P1-C/P1-D khi chưa có nhãn; calibration, so sánh chất lượng, benchmark và P2 được để sau. Đây là cập nhật phạm vi sau lần bàn giao mục 17, không phải kết luận đã đạt cổng calibration/rollout.

- P1-C: candidate khi local **hoặc** global cosine distance vượt ngưỡng cấu hình. Candidate được xác nhận bằng ít nhất hai sample mới, đủ thời gian confirmation cấu hình; sample xác nhận phải cách centroid pending không quá ngưỡng global đã cấu hình. Min-duration mềm chỉ chặn global-only; local change đã xác nhận được cắt sớm. Pending chưa xác nhận nhập về scene cũ khi EOF/gap/hard max; sample quay về sau flash không lập tức tạo candidate mới trên chính return edge đó. Hard max 5 giây vẫn ưu tiên. Không có threshold runtime tự đặt.
- `exhaustive`: người dùng xác nhận không báo true khi phạm vi tìm kiếm có evidence v2, kể cả khi hoàn tất VLM trên các frame đã chọn. Xác định phạm vi bằng video/dataset/thời gian/granularity trước hậu kiểm semantic; v2 ở ngoài phạm vi không làm đổi cờ của legacy. `degraded` tiếp tục chỉ phản ánh lỗi retrieval tower.
- Runtime mặc định `VIDEO_SCENE_SEGMENTATION=time`. Chọn `content_time` phải cung cấp local/global distance, min-duration và confirmation duration. `scene_calibration_version` được lưu trong snapshot nếu có; việc cho phép cấu hình để thử nghiệm không chứng minh các giá trị đã calibration.
- P1-D mặc định `VIDEO_VLM_MAX_FRAMES=1`, giới hạn 3. Khi chọn nhiều hơn một frame phải cung cấp `VIDEO_VLM_NOVELTY_DISTANCE`; không có novelty default. Budget mặc định giữ concurrency 2, timeout 30 giây, tối đa 2 attempts/frame. Giữ provider/model/prompt hiện có, không thêm lần gọi tổng hợp caption.
- Chọn farthest-point theo min cosine distance đến tập đã chọn; tie-break khoảng cách thời gian rồi timestamp/index tăng dần. Candidate phải vượt novelty threshold mới được thêm; không padding. Quality dùng cùng cơ chế đã có nếu được bật với ngưỡng đã cung cấp.
- Tách quyết định dedup và đóng ảnh: medoid được chọn từ toàn sample, mode middle vẫn lấy retained để giữ baseline. Candidate VLM chọn từ toàn sample còn mở; sau khi biết retained/representative/candidate mới đóng các ảnh không cần. Không thêm candidate bị dedup vào Qwen.
- Mọi threshold số trong test là fixture tổng hợp. Không dùng video ở `D:\User_Files\datadoan` hoặc caption VLM làm ground truth trong lượt kiểm thử này; không chạy reindex thật.

### 1.6. Cập nhật phạm vi được người dùng xác nhận (23/11/2026)

Mục này thay thế các yêu cầu trước đó khi có xung đột; mục 17–19 giữ làm lịch sử thực hiện.

1. Đề xuất 3: cho phép bộ ngưỡng thử nghiệm local distance 0.10, global distance 0.15, min-duration mềm 2 giây, confirmation 0.4 giây (vẫn ít nhất hai sample), max scene 5 giây. Đây là heuristic chưa calibration, không suy ra trực tiếp từ dedup similarity 0.98. Có comment chỉ cách điều chỉnh; snapshot ghi đúng giá trị resolved. Giữ default code `time`; cấu hình local và file mẫu dùng `content_time`. Không thay FPS, dedup, nguồn ảnh embedding hoặc ngân sách VLM. Version calibration không được bịa thành kết quả đo.
2. Đề xuất 6: bỏ quality filter (Laplacian/clipping), quality tie-break và các cấu hình liên quan ở cả representative và VLM candidates. Giữ medoid theo SigLIP, tie-break gần midpoint rồi timestamp/index; giữ middle để tương thích, thumbnail cố định và fail-closed nếu không có derivative verified. JPEG compression quality không phải quality filter và giữ nguyên.
3. Đề xuất 9: ingest lại từ đầu sau reset local đã thực hiện ở mục 19. Không triển khai công cụ chuyển đổi/backfill/reindex/snapshot/rollback dữ liệu cũ hoặc canary/batch rollout trong phạm vi này. Giữ migration schema, fingerprint, preflight, retry/cleanup/cancellation và invalidation để bảo vệ ingestion mới; không xóa code tương thích legacy hoặc migration hiện có.
4. Đề xuất 10: không triển khai evaluator, sửa evaluator hay benchmark retrieval có nhãn. Vẫn thực hiện unit/integration/regression phù hợp cho thay đổi code. Người dùng chạy smoke hệ thống/model/provider/video thật; ghi đây là phần chưa thực hiện cho đến khi có kết quả, không coi code tests là bằng chứng chất lượng thực tế.

## 2. Hiện trạng tại thời điểm lập kế hoạch (lịch sử trước triển khai)

| Thành phần | Hiện trạng | Điểm cần xử lý |
| --- | --- | --- |
| `app/pipelines/ingestion/orchestrator.py` | Sample → anonymize/verify → metadata timestamp/tracking/behavior → SigLIP → dedup toàn video → Qwen → scene builder → VLM → pooling → media → persistence | Đổi thứ tự, ownership ảnh, metrics và version |
| `scene_builder.py` | Cắt theo timestamp, max duration và gap; cuối scene dùng coverage + sample interval | Có thể vượt max duration; chưa chia theo nội dung |
| `deduplicator.py` | So với frame cuối được giữ, mở rộng coverage rồi đóng ảnh frame bị loại | Không được chạy xuyên scene; ảnh candidate có thể bị đóng trước thumbnail/VLM |
| `embedder.py` | Mean rồi L2; Qwen có fallback `qwen_embedding or embedding` | Tách pooling source, bỏ fallback xuyên model, kiểm tra mọi vector |
| `preview_generator.py` | Thumbnail từ `keyframes[len(...) // 2]`; một playback/video | Thêm representative rõ ràng, giữ playback hiện tại |
| `metadata_extractor.py` | VLM chỉ frame đầu; fallback gán day/clear/residential, absent night/rain | Tổng hợp evidence có timestamp; unknown đúng nghĩa |
| `indexer.py` | Metadata và `frame_id` từ frame đầu; fallback giả định lặp lại | Một nguồn metadata/fallback; đồng bộ representative và trường filter |
| `app/search/catalog.py` | `Keyframe` dùng chung cho frame/segment; timestamp ưu tiên `video_second`; concept arrays từ structured fields/caption | Cần adapter schema mới, tách timestamp scene/thumbnail, đọc evidence |
| `app/search/engine.py` | ANN pushdown theo `present_concepts`; hậu kiểm catalog/caption; RRF và gom theo video | Hai đường đọc cần thống nhất, hậu kiểm đồng thời trong scene |
| `app/search/points.py` | Filter weather/timeofday/scene ở các trường top-level | Payload mới phải ghi đúng các trường này, không chỉ `metadata.scene.*` |
| `app/services/caption_refresh.py` | Đọc một thumbnail, dựng scene một frame, cập nhật caption/concepts; tăng Redis generation | Không được ghi đè scene evidence mới bằng một thumbnail |
| `app/services/datasets.py` | Export lookup point qua catalog, lấy timestamp/caption/thumbnail | Giữ scene span, bổ sung timestamp đại diện nếu cần |
| `app/repositories/corpus.py`, `db/models/corpus.py` | Pipeline chính chỉ insert segment, chưa insert frame; `Segment.keyframe_id` là FK đến `frames.id` | Không gán decoded frame index vào FK; cần cột representative riêng |
| `app/api/v1/ingestion.py`, `worker/tasks/ingestion.py` | API có `force` qua claim status; worker gọi orchestrator bằng task/video ID; pipeline version chưa truyền xuyên task | Version/config phải thống nhất từ lúc enqueue đến worker |
| `app/search/index.py` | Reindex delete-before-upsert; dimension check còn lỏng; một số named collection bị bảo vệ read-only | Preflight schema/quyền trước delete; không mặc định mọi collection đều ghi được |
| `app/eval/runner.py`, `truth.py` | Chấm theo video/frame_no; `frame_no=0` bị `or -1`; behavior dùng frame_no/fps | Thêm scene interval và representative timestamp; giữ zero hợp lệ |

Hai trường hợp biên đã tái hiện ở lần review trước bằng hàm stage gốc, container record giả lập, sampling 1 fps: sample ở 0–5 giây có thể thành `[0,6)`; sample giống nhau ở 0–10 giây sau dedup có thể thành `[0,11)`, dù cấu hình max 5 giây. Đây là kiểm tra logic cô lập, không phải benchmark end-to-end.

Các tài liệu cũ trong `../../docs/Ke_hoach_Thuc_Hien_Ingestion` (đường dẫn tính từ repo root) có nhiều hướng mở rộng độc lập; kế hoạch này không mặc định gộp MOT, adaptive sampling, async VLM hay frame indexing vào phạm vi.

## 3. Luồng đích và dữ liệu trung gian

```text
Acquire + probe video (trả thông tin duration/timeline)
  → Decode + sample (giữ timestamp nguồn và lý do khoảng trống)
  → Anonymize + verify (giữ gate hiện tại)
  → Metadata timestamp / tracker / behavior interface hiện tại
  → SigLIP theo batch trên mọi sample verified
  → Scene Builder trên chuỗi sample chưa dedup
      ├─ khoảng [start, end), max 5 s, gap thực
      ├─ time-only baseline hoặc content + time
      └─ tổng SigLIP và số sample của từng scene
  → Chọn representative + tối đa 3 VLM candidate từ sample scene
  → Dedup riêng từng scene (không đóng candidate còn người dùng)
  → Qwen encode retained frames, gom batch giữa các scene khi cần
  → Pooling: SigLIP toàn sample; Qwen retained; L2 normalize riêng
  → VLM candidate đã anonymize + tổng hợp scene evidence
  → Thumbnail representative + full-video playback
  → Validate toàn bộ output / preflight persistence
  → Persist Postgres + Qdrant theo cơ chế thay thế đã kiểm chứng
  → Publish trạng thái indexed + invalidate catalog
```

Thiết kế record đề nghị, tên trường mới là dự kiến triển khai:

- `FrameRecord`: giữ `timestamp_ms` và `frame_index` decoded; chuẩn hóa rõ sample coverage độc lập với coverage sau dedup. Không suy timestamp bằng `frame_index / SEARCH_KEYFRAME_FPS` cho video mới.
- `SceneRecord.keyframes`: quy định là retained frame sau dedup khi sang bước Qwen/persistence; trước dedup dùng một scene draft hoặc collection sample tạm rõ ràng.
- Scene draft giữ sample count, SigLIP sum/count, candidate reference, start/end, boundary reason. Không giữ mọi ảnh đã decode của video lâu hơn cần thiết.
- Scene output giữ representative index/timestamp/selection method, pooling metadata, sample/retained count và scene evidence có schema version.
- Không để một danh sách `keyframes` vừa mang nghĩa toàn sample vừa retained mà không có bước chuyển và test rõ ràng.
- Frame thumbnail/VLM có thể thuộc sample bị dedup: giữ reference/bản copy derivative đến khi sử dụng xong, nhưng không tự thêm nó vào Qwen pooling. Quy tắc D1 vẫn giữ nguyên.

## 4. Đề xuất 1 — Thời gian và coverage chính xác

**Ưu tiên:** P0. **Phụ thuộc:** hợp đồng timeline. **Ảnh hưởng search:** sửa span trả về, không đổi ranking.

### Công việc

1. Cho bước probe/validate trả về một record media có duration tin cậy, time base và nguồn duration, thay vì chỉ `None`. Không tạo một lần decode toàn video bổ sung chỉ để lấy duration.
2. Chọn timeline cùng hệ với playback; xử lý PTS bắt đầu khác zero, VFR, timestamp trùng/lùi bằng quy tắc có log và fixture. Không giả định decoded index là timestamp.
3. Định nghĩa sample interval là half-open `[a,b)`; tách khỏi định nghĩa hiện tại trong đó `covers_end_ms` là timestamp sample cuối rồi được cộng interval ở Scene Builder.
4. Bản đầu: với sample t, kết thúc danh nghĩa là `t + sample_interval_ms`, chặn ở sample kế tiếp, ranh giới scene và video end đã biết. Không lấp khoảng mất dữ liệu/privacy failure bằng cách kéo coverage qua đó.
5. Cần one-sample lookahead/EOF context để chốt cuối sample. Nếu metadata duration thiếu, dùng timestamp/frame-duration decode quan sát được, đánh dấu nguồn estimated; không quảng cáo thời lượng chính xác nếu chỉ có ước lượng.
6. Khi chạm max duration, cắt tại ranh giới hợp lệ không vượt `start+5000`; không dùng điều kiện `last_timestamp-first_timestamp > max` như hợp đồng cuối cùng. Khi sample cadence thưa không có ảnh đúng ranh giới, không bịa frame hoặc duplicate point không có bằng chứng; mô tả rõ các khoảng không được đại diện.
7. Khi ranh giới nội dung nằm tại sample t, scene trước kết thúc không sau t; sample t vào scene mới. Scene không rỗng, `0 <= start < end`, duration không vượt max, representative nằm trong khoảng.
8. Dùng kiểm tra `is not None` cho timestamp/coverage; zero là hợp lệ. Áp dụng cùng nguyên tắc cho frame index.

### File và nghiệm thu

Sửa `video_reader.py`, `sampler.py`, `scene_builder.py`, `common/types.py`, orchestrator và fixture liên quan. Giữ API `validate_video` tương thích hoặc cập nhật đầy đủ caller/test.

Test: duration lẻ, EOF < một sample interval, sample tại đúng mốc 5 s, video đứng yên dài, VFR, missing frame, privacy rejection, timestamp zero, PTS không zero. Khoảng missing được ghi nhận; không khẳng định timeline phải liền mạch khi dữ liệu thiếu thật.

## 5. Đề xuất 2 — Chia scene trước dedup và quản lý vòng đời ảnh

**Ưu tiên:** P0/P1. **Phụ thuộc:** đề xuất 1. **Ảnh hưởng search:** đổi scene inventory, giữ giao thức truy vấn.

### Công việc

1. Di chuyển `build_scenes` lên sau SigLIP và trước `filter_near_duplicates`; reset `previous` của dedup tại mỗi scene.
2. Giữ ít nhất một retained frame cho scene hợp lệ. Không gộp coverage từ scene trước sang scene sau, dù vector giống hệt.
3. SigLIP accumulator thu mọi sample trước dedup; count phản ánh số sample thật. Không tính lại SigLIP sau dedup hoặc khi chọn thumbnail.
4. Tách quyết định loại frame khỏi hành động đóng ảnh. Candidate thumbnail/VLM không được đóng đến khi consumer cuối dùng xong; dùng ownership rõ ràng và `finally` cleanup khi inference/upload/persist lỗi.
5. `embed_frames` hiện `list(...)` toàn iterable; thay bằng iterator batch hoặc giới hạn materialization để bounded theo batch/scene. Giữ wrapper tương thích nếu các caller/test cần list.
6. `owned_frames` hiện lưu reference mọi decoded frame; thay bằng cơ chế quản lý active frame để đóng frame đã tiêu thụ và không tăng bộ nhớ theo toàn video. Không chỉ đổi tên hàm rồi gọi đó là streaming.
7. Qwen có thể batch retained frame từ nhiều scene, nhưng phải giữ ánh xạ scene/frame đúng và tuân thủ batch size hiện tại.
8. Đổi progress stage cho đúng thứ tự; metrics phân biệt `sampled_frames`, `retained_frames`, `dedup_dropped`, `scene_count`. Hiện metric sampled chỉ đếm retained nên cần đổi nghĩa có version.

### File và nghiệm thu

Sửa `orchestrator.py`, `deduplicator.py`, `embedder.py`, types/context nếu cần. Tests bảo đảm không dedup xuyên scene, không dùng ảnh đã close, cleanup ở lỗi SigLIP/Qwen/VLM/thumbnail và không tăng ảnh active tuyến tính với độ dài video.

## 6. Đề xuất 3 — Content-aware Scene Builder có giới hạn thời gian

**Ưu tiên:** P1. **Phụ thuộc:** 1, 2, vector contract ở 4. **Ảnh hưởng search:** đổi ranh giới scene và vector đại diện.

### Thuật toán bản đầu

1. Giữ mode `time` làm baseline đã sửa tính đúng; thêm mode `content_time` qua cấu hình.
2. Tính `d_local = 1 - dot(normalize(e_t), normalize(e_prev))` và `d_global = 1 - dot(normalize(e_t), normalize(sum_current))` trong không gian SigLIP. Clamp sai số số học của cosine.
3. Dùng ngưỡng local/global đã calibration để tạo candidate boundary. Frame candidate chưa được cộng vào centroid scene cũ cho đến khi quyết định xong.
4. Xác nhận bằng buffer: có ít nhất hai sample thuộc chế độ mới, cách nhau đủ thời gian xác nhận, và nhất quán với anchor/centroid candidate; không chỉ yêu cầu mọi cặp frame mới có local distance cao.
5. Nếu thay đổi không duy trì, trả buffer về scene cũ theo thứ tự. Nếu duy trì, đặt ranh giới tại candidate onset và chuyển cả buffer phù hợp sang scene mới.
6. Max 5 s và gap thực ưu tiên hơn min duration mềm. EOF, thiếu sample xác nhận và chạm max khi đang pending phải có nhánh xử lý deterministic.
7. Chưa tối ưu backtracking quanh hard max trong bản đầu; không để việc tìm vị trí đẹp làm scene vượt max. Không suy ra hành động/quan hệ từ boundary.
8. Boundary reason lưu `content_local`, `content_global`, `max_duration`, `data_gap`, `eof` hoặc enum tương đương, cùng khoảng cách để debug.

### Cấu hình và ngưỡng thử nghiệm theo xác nhận 1.6

- Tận dụng `VIDEO_SEGMENT_SECONDS=5.0` làm max, không thêm biến max thứ hai.
- Default code vẫn `time`; `app/.env.local.example`, `app/.env.example` và cấu hình local `app/.env` dùng `content_time` với local distance 0.10, global distance 0.15, min-duration mềm 2 giây, confirmation 0.4 giây. Không thay sampling FPS hoặc dedup.
- Ngưỡng đều là **cosine distance = 1 - cosine similarity**. Tăng local/global threshold làm khó tạo boundary hơn; giảm làm nhạy hơn. Global threshold đồng thời là bán kính consistency của pending centroid, nên tăng global cũng làm bước xác nhận chấp nhận buffer rộng hơn.
- Local so sample liên tiếp; global so sample mới với centroid scene hiện tại. Min-duration mềm chỉ áp dụng global-only. Confirmation luôn cần ít nhất hai sample; tại 1 fps thời gian thực tối thiểu là một khoảng sample dù cấu hình 0.4 giây.
- Đây là heuristic được người dùng cho phép, không phải ngưỡng đã calibration và không suy ra trực tiếp từ dedup similarity 0.98. Không gán version calibration giả. Giá trị resolved vẫn vào fingerprint/snapshot để đối chiếu khi người dùng điều chỉnh.
- Khi chọn `content_time` mà thiếu cấu hình bắt buộc, vẫn báo cấu hình thiếu. Không chuyển âm thầm về time hoặc chèn giá trị khác; default numeric trong code vẫn unset, các giá trị thử nghiệm nằm tường minh trong cấu hình local/file mẫu.

### Nghiệm thu trong phạm vi hiện tại

Fixture embedding cho hard cut, gradual drift, flash một sample, jitter, pending ở EOF/max và cadence 1/5 fps; kiểm tra ranh giới, thứ tự frame, frame membership và pooling. Có test dùng đúng ngưỡng local thử nghiệm đã chốt. Kết quả trên video thật do người dùng chạy smoke theo mục 20; không yêu cầu triển khai evaluator hoặc lấy nhãn để hoàn tất code chức năng.

## 7. Đề xuất 4 — Pooling riêng từng model và vector contract ảnh/text

**Ưu tiên:** P0 cho validation; P1 cho pooling source. **Phụ thuộc:** 2. **Ảnh hưởng search:** dữ liệu vector thay đổi, tower/ranking giữ nguyên.

### Công việc

1. Đặt contract tại encoder boundary: đúng số output, đúng dimension model, mọi phần tử finite, norm > epsilon; chuẩn hóa L2 cho cả `encode_images` và `encode_texts`.
2. SigLIP remote hiện trả trực tiếp response: bổ sung kiểm tra và chuẩn hóa, kể cả text. Qwen remote đã normalize nhưng cần kiểm tra mọi row thay vì chỉ row đầu; local output cũng cùng contract.
3. D1: `siglip_scene = normalize(sum(unit_siglip_of_all_verified_scene_samples))`; `qwen_scene = normalize(sum(unit_qwen_of_retained_frames))`. Mean và sum sau normalize có cùng hướng khi trọng số bằng nhau.
4. Accumulator SigLIP phải được gắn với scene sau boundary confirmation; frame chuyển sang scene mới không được ở sum scene cũ. Dùng vector sum/count làm đầu vào pooling rõ ràng.
5. Bỏ `frame.qwen_embedding or frame.embedding` trong hybrid path. Thiếu Qwen phải encode bằng Qwen từ ảnh còn sống hoặc fail stage rõ ràng; không thay bằng SigLIP 768-d.
6. Kiểm tra mọi point và đúng dimension theo vector name tại write path, không chấp nhận tùy ý 768 hoặc 2048 cho mọi tên. Giữ stub dimension trong single-encoder test bằng contract được inject, không hardcode production dimension vào mọi unit test.
7. Nếu tổng vector gần zero, fail scene có chẩn đoán; không lưu zero vector, không tự chuyển sang medoid làm search vector vì đó là đổi thuật toán ngoài cấu hình.
8. Ghi `pooling_method`, `pooling_source`, input count và model version riêng cho từng tower. Duration-weighted Qwen/SigLIP chỉ là ablation tùy chọn, không bật mặc định.

### File và nghiệm thu

Sửa `embedder.py`, `ml/encoder.py`, `ml/qwen_encoder.py`, `search/index.py`; có thể thêm utility vector thuần để dùng chung, không import pipeline vào search.

Test ảnh/text local/remote qua stub: non-unit input, sai số row count, sai dimension row sau, NaN/Inf, zero, batch mapping, thiếu Qwen. Kiểm chứng score cosine giữa vector hợp lệ không bị đổi bởi chuẩn hóa lặp; so sánh image/text phải cùng model/preprocessing version.

## 8. Đề xuất 5 — Frame đại diện rõ ràng, tách timestamp khỏi scene start

**Ưu tiên:** P1. **Phụ thuộc:** 1, 2. **Ảnh hưởng search:** adapter/API/export cần hiểu đúng timestamp, không đổi ANN/RRF.

### Dữ liệu và persistence

- Scene output: representative frame index decoded, timestamp ms, selection method/version, score và fallback reason nếu có.
- Postgres: migration thêm các cột nullable representative index/timestamp/method và thumbnail object key vào `segments` để có provenance media phục vụ kiểm tra/rollback. Không sử dụng `Segment.keyframe_id` trừ khi thực sự insert một hàng `Frame` có UUID tương ứng.
- Cập nhật `SegmentRow`, `insert_segments` insert/upsert column list và orchestrator mapping; dữ liệu cũ vẫn nullable. Quy định `frame_count` là retained count; thêm sampled count riêng nếu cần thống kê, không đổi ngầm nghĩa.
- Payload Qdrant giữ `frame_id`/`frame_name` tương thích theo frame đại diện, thêm trường representative có kiểu rõ ràng. Payload index `frame_id` hiện KEYWORD dù pipeline ghi số: dùng trường mới INTEGER cho decoded index, không âm thầm đổi kiểu index legacy.
- `ts_start_s`, `ts_end_s`, `start_ms`, `end_ms`, legacy `video_second` tiếp tục biểu diễn scene span/start. Không đổi `video_second` sang thumbnail time vì frontend đang ưu tiên nó khi seek.
- Bổ sung response optional `representative_timestamp_s`, `representative_frame_index`; áp dụng cả primary result và `matched_moments`. Với legacy không có thông tin thì để null, không suy ra chắc chắn.

### Adapter/consumer

`Keyframe.timestamp_s` tiếp tục là scene start cho segment; thêm timestamp đại diện riêng. Đối với schema scene mới, ưu tiên trường scene start có nghĩa rõ; không lấy representative time làm start. Giữ frame legacy behavior.

Cập nhật `schemas/search.py`, `api/v1/search.py`, `search/catalog.py`; kiểm tra `frontend/src/lib/searchApi.js`, player/seek, `services/datasets.py`, chat-agent consumer và export manifest. Export vẫn có span; timestamp/frame đại diện được bổ sung để đối chiếu thumbnail. Không cần viết lại UI nếu trường mới chỉ là thông tin bổ sung.

### Nghiệm thu

Scene `[10,15)` có thumbnail 13 s: API/seek vẫn bắt đầu 10 s, representative là 13 s, frame_no khớp ảnh; round-trip Postgres/Qdrant/API/export; frame index zero hợp lệ; đọc được payload v1/offline.

## 9. Đề xuất 6 — Medoid cho thumbnail, không quality filter

**Ưu tiên:** P1. **Phụ thuộc:** 4, 5. **Ảnh hưởng search:** thumbnail cố định tại ingestion; giữ phép pooling và ranking hiện có.

### Công việc theo xác nhận 1.6

1. Input selector là toàn sample hợp lệ của scene và SigLIP centroid; chỉ chọn frame có derivative verified.
2. Chọn candidate có cosine cao nhất với SigLIP centroid (cosine medoid với unit vector/trọng số đều); không tính all-pairs O(N²).
3. Bỏ toàn bộ quality filter Laplacian/clipping, quality tie-break và các cấu hình threshold/version liên quan. Áp dụng cả representative và VLM candidates. Không phân tích độ nét/độ sáng để loại frame.
4. Tie-break deterministic: similarity, gần temporal midpoint, timestamp rồi decoded index. Ghi version `cosine-medoid-v2`, similarity và representative reference.
5. Giữ mode `middle` để tương thích. Không có derivative verified usable thì fail-closed; không dùng raw để chữa thumbnail.
6. Representative được bảo vệ đến lúc stage thumbnail; không reorder timeline hoặc thêm representative bị dedup vào Qwen. Preview chỉ consume frame đã chọn.
7. Giữ JPEG compression quality và kích thước thumbnail hiện có; đây là tham số lưu ảnh, không phải bộ lọc ảnh.

### Nghiệm thu

Scene một frame, duplicate tie, medoid khác middle, mọi ảnh tối/flat vẫn chọn được, derivative thiếu/chưa verified bị từ chối, representative bị dedup vẫn dùng được và không vào Qwen. Kiểm tra đúng timestamp/pixel/source của thumbnail xuất ra. Các test chất lượng cũ được thay bằng test hành vi mới vì chức năng quality đã được người dùng bỏ khỏi phạm vi.

## 10. Đề xuất 7 — Metadata scene có bằng chứng theo frame và đọc search nhất quán

**Ưu tiên:** P1. **Phụ thuộc:** 5, 6 và fallback ở 8. **Ảnh hưởng search:** đồng bộ filter/hậu kiểm là phần được D4 cho phép; không thay rank fusion.

### 10.1. Candidate và ngân sách VLM theo D2

- Chọn tối đa 3 frame index khác nhau: representative trước, sau đó candidate khác biệt SigLIP nhiều nhất so với tập đã chọn, có ưu tiên khoảng cách thời gian để tránh ba ảnh gần như cùng lúc.
- Ngưỡng novelty cấu hình được; scene một ảnh hoặc đồng nhất có thể chỉ gọi một lần. Không padding lên 3 bằng frame lặp. Không quality filter theo xác nhận 1.6; default vẫn một frame, muốn nhiều hơn một phải cung cấp novelty threshold tường minh.
- Candidate chọn trước dedup và giữ `display_image` đến lúc VLM xong; không bắt buộc encode Qwen cho các candidate này.
- Cấu hình max candidates, concurrency, timeout và retry budget. Phân biệt tối đa 3 frame với tối đa 3 HTTP request: retry có thể tăng request count, phải đo riêng và có giới hạn.
- Giữ API VLM provider/prompt JSON hiện tại rồi bổ sung validation schema; chưa thêm một lần gọi LLM để viết lại caption tổng hợp.

### 10.2. Schema evidence đề nghị

Mỗi observation có `frame_index`, `timestamp_ms`, `source`, `status`, caption, thuộc tính, positive/explicit-negative concepts, model/prompt version; optional confidence chỉ ghi nếu có cơ sở, không tự đặt 1.0 cho suy luận VLM.

Scene metadata giữ `schema_version`, danh sách observations, sampled/candidate/succeeded count, coverage của việc quan sát, summary attributes và representative reference. Tách trạng thái `complete_for_selected_frames` khỏi khẳng định đã quan sát mọi thời điểm video.

Caption tổng hợp để hiển thị/lexical có timestamp và mệnh đề riêng, ví dụ “10.2 s: xe buýt ...; 13.0 s: người đi bộ ...”. Không ghép thành một câu quan hệ mới. Bản đầu có thể giữ caption đại diện làm summary và dùng evidence cho retrieval, nhưng mọi đường đọc phải cùng chính sách.

### 10.3. Quy tắc tổng hợp

- `present_concepts`: có quan sát dương tính ở ít nhất một frame thành công; là tín hiệu tồn tại trong scene, không phải đồng thời.
- Một frame ghi absent không đủ để tạo phủ định toàn scene. Bản đầu không ghi scene-level absence nếu không có bằng chứng phủ đủ khoảng cần khẳng định; giữ explicit negative ở observation scope.
- Thuộc tính ổn định: dùng khi observation hợp lệ nhất quán; nếu mâu thuẫn thì scene summary là unknown/mixed theo schema và giữ chi tiết. Không để frame đầu áp đặt weather/time cho cả đoạn.
- Không suy ra “người đứng cạnh xe buýt” hoặc hành động chỉ vì hai khái niệm có ở hai frame. Điều kiện quan hệ/hành vi cần cùng observation chứa bằng chứng tương ứng, và vẫn chỉ là quan sát VLM chứ không phải tracking temporal mới.
- Với nhóm điều kiện cần đồng thời trong D4, hậu kiểm phải tìm ít nhất một observation đáp ứng cả nhóm. Truy vấn temporal như “sau đó” chưa có logic mới; không tự diễn giải thành AND đồng thời.
- Đếm object là per-observation; `max_object_counts` theo lớp không chứng minh tổng hợp đồng thời nhiều lớp ở các thời điểm khác nhau.

### 10.4. Đồng bộ đường đọc

1. Qdrant dùng scene-level positives làm pushdown broad filter hợp lệ; việc chứng minh cùng frame thực hiện ở hậu kiểm candidate. Không thay candidate retrieval thành filter per-frame làm mất scene không có đủ enrichment mà không ghi rõ strictness.
2. `catalog.Keyframe`/`CatalogView` giữ evidence v2; `_resolve_concepts`, `_verdict_at`, `_admissible_keyframes` và stateless candidate-cache path dùng chung resolver v2. Không chỉ cập nhật một nhánh.
3. Schema v1 tiếp tục resolver structured/caption hiện tại; schema v2 đọc explicit evidence, tránh caption timestamp tổng hợp tạo co-occurrence giả.
4. Unknown là unknown: strict required không được “confirmed” nếu thiếu evidence; non-strict vẫn giữ semantics hiện có ở mức không khẳng định. Query exclude loại khi có positive; không báo `denied` khi chỉ thiếu positive. Giữ cờ exhaustive/degraded trung thực.
5. Payload builder đồng bộ top-level weather/timeofday/scene/objects/concepts với metadata summary theo đúng tên field của `build_filter`; tránh top-level và nested mâu thuẫn. Khi summary unknown, bỏ trường filter known-value tương ứng.
6. Test query nhiều required/min counts cả trên catalog loaded và ANN payload chưa có trong snapshot; kiểm tra symmetry pushdown/postfilter, canonical concept mapping và schema legacy.
7. `caption_refresh` phải đọc schema/status mới. Refresh từ một thumbnail chỉ cập nhật observation tương ứng hoặc đánh dấu thumbnail-only; không ghi đè evidence scene, không tự nhận có lại 3 frame khi không lưu các ảnh đó. Cần full reingest để tái tạo multi-frame evidence nếu chỉ còn một thumbnail.

### File và nghiệm thu

Sửa `metadata_extractor.py`, `indexer.py`, `search/catalog.py`, `search/engine.py`, `search/points.py` khi cần, `services/caption_refresh.py`, payload indexes và test. Có thể tách `scene_metadata.py`/`scene_evidence.py` dùng chung schema/resolver; tránh vòng import API/pipeline/search.

Case bắt buộc: người chỉ ở cuối scene; A và B ở hai frame riêng; A+B cùng frame; thuộc tính mâu thuẫn; VLM thành công 1/3, lỗi 3/3; query phủ định; concept không được nhắc; legacy captions; candidate-cache vs catalog; refresh không làm mất evidence.

## 11. Đề xuất 8 — Fallback unknown có provenance

**Ưu tiên:** P0, làm trước metadata nhiều frame. **Phụ thuộc:** schema dữ liệu, có thể triển khai độc lập. **Ảnh hưởng search:** loại bằng chứng giả định.

### Công việc

1. Dùng một builder fallback có schema chung cho `metadata_extractor`, `indexer` và refresh. Bỏ các bản fallback day/clear/residential/car/road và absent night/rain không có quan sát.
2. Unknown ở trường enum; null/bỏ trường đối với bool/count chưa biết theo schema. Không dùng `false`, `0`, `none` hay empty observed array để biểu diễn extractor chưa chạy.
3. Chỉ ghi objects/detections có nguồn thực. `extract_metadata` hiện chỉ thêm timestamp và detector behavior đang noop; không giả định pipeline đã có object detection traffic đầy đủ.
4. Tách technical fallback message khỏi semantic caption. Có thể để caption rỗng và ghi reason ở enrichment status; cập nhật refresh selector và search unknown handling đồng thời để không phụ thuộc regex template cũ.
5. Status ít nhất phân biệt `not_configured`, `failed`, `partial`, `success`; error code không chứa API key hoặc payload ảnh.
6. Validate VLM JSON bằng schema, canonicalize concept/enum, xử lý invalid/contradictory field thành unknown có reason. Parse được JSON chưa đủ để coi metadata hợp lệ.
7. Lỗi enrichment không làm mất toàn video nếu vector/privacy/media hợp lệ; trạng thái partial thể hiện ở payload/task metrics. Không ghi “completed semantic enrichment” khi VLM lỗi hết.

### Nghiệm thu

Không có API key, timeout/429, JSON sai, response rỗng, detector chưa chạy: không tự sinh car/day/clear/absence; night/rain query không bị phủ định do fallback. Đọc unknown traffic không được chuyển thành “pedestrians: unknown” rồi coi là positive trong catalog.

## 12. Đề xuất 9 — Version, persistence và reindex có thể kiểm chứng

**Ưu tiên:** P0 cho nền version/preflight; P2 cho rollout. **Phụ thuộc:** schema các đề xuất 1–8.

### 12.1. Version và DB migration

- Một nguồn version/config fingerprint: segmentation, pooling source/method, representative algorithm, metadata schema/prompt, sample FPS/dedup threshold, encoder/preprocessing version từng tower.
- Hash từ cấu hình canonical không chứa secret; lưu config resolved có chọn lọc để tái hiện. Đổi fingerprint khi output có thể đổi; không chỉ so `encoder.model_version`.
- Thêm `ingestion_pipeline_version`/`ingestion_fingerprint` vào Video nếu cần skip theo output hoàn chỉnh; thêm representative và fingerprint/provenance phù hợp vào Segment. Giữ model_version cho model, không nhồi toàn pipeline vào đó.
- Truyền version/fingerprint qua API enqueue → task → orchestrator → task status/payload/DB; không để API ghi v2 còn worker default v1. Job đã enqueue dùng snapshot config hoặc fail rõ khi snapshot không được hỗ trợ.
- Duy trì `force` qua đường reprocess hiện có; kiểm tra worker direct-call skip và API duplicate-check đều xét fingerprint đúng. Không kết luận force đang hỏng: API hiện claim status processing trước enqueue nên đã có cơ chế vượt duplicate.
- Kiểm tra Alembic graph/head thật trước khi tạo revision; không đặt `down_revision` theo ngày file. Migration nullable cho legacy; không backfill representative bằng frame đầu rồi gọi là kết quả medoid.

### 12.2. Preflight và thay thế

1. Validate toàn bộ scenes/vectors/payload/media trước khi delete dữ liệu cũ. Hiện `build_scene_points` nằm sau delete/insert nên cần chuyển phần build/validation lên trước destructive persistence.
2. Preflight target collection: write ownership, named vectors đúng dimension/metric, payload indexes, Postgres migration và storage. `_refuse_if_read_only` phải được tôn trọng; không sửa guard để ghi vào collection chưa xác định sở hữu. Collection canary mới cần cấu hình tạo đủ hai vector: initializer hiện chỉ tự thêm `siglip` khi `write_vector_name=qwen` và `vector_size=2048`; mặc định 768/unnamed không tương thích pipeline hybrid. Dùng cấu hình target đúng hoặc thêm schema profile tường minh; không sửa collection legacy tại chỗ. Initializer hiện bỏ qua tạo payload indexes trên hybrid collection đã tồn tại: phải có bước provision indexes riêng cho collection được sở hữu, không tưởng chúng luôn có sẵn.
3. Giữ id deterministic theo video/pipeline version/scene index cho run cùng fingerprint. Khi config thay đổi làm boundary đổi, ID/provenance phải phân biệt; không trộn generation rồi dựa vào upsert để xóa orphan.
4. Tránh delete Qdrant hai lần giữa orchestrator và `reindex_video`; một owner chịu trách nhiệm replace. Giữ kiểm tra cancellation ở các stage và trước publish.
5. Postgres/Qdrant/MinIO không có transaction chung. Không tuyên bố zero-downtime hoặc rollback nguyên tử; lỗi từng phần phải được báo rõ và xử lý retry/cleanup theo cơ chế hiện có. Công cụ backup/khôi phục dữ liệu cũ được bỏ khỏi phạm vi ingest mới theo xác nhận 1.6.
6. Với staged collection, cần DB/output namespace tách biệt tương ứng hoặc snapshot/reconcile DB; chỉ đổi Qdrant collection mà dùng chung unique `(video_id, segment_index)` trong Postgres chưa phải isolation đầy đủ.
7. Media mới theo job key; lỗi trước publish chỉ cleanup media thuộc job hiện tại. Media generation cũ chỉ GC sau khi publish/reindex xác nhận và kiểm tra không còn tham chiếu; không xóa raw hoặc playback đang được dùng.
8. Sau publish, tăng Redis catalog generation bằng helper dùng chung với caption refresh. Dữ liệu mới, delete và failure cleanup có thay đổi index đều cần invalidation thích hợp. Redis lỗi có log/TTL fallback; không biến lỗi signal sau publish thành cleanup dữ liệu đã publish.
9. Kiểm tra cursor generation, metadata snapshot, thumbnail cache theo object key và optional image-reranker cache. Ảnh mới dùng key mới; không cần flush Redis toàn hệ thống.

### 12.3. Phạm vi dữ liệu mới sau reset local

- Reset local đã thực hiện và kiểm chứng ở mục 19; người dùng sẽ ingest mới từ video nguồn. Không triển khai snapshot/restore dữ liệu cũ, backfill, reindex/canary/batch rollout trong lần này.
- Giữ fingerprint/snapshot cấu hình (khác backup dữ liệu), schema migration hiện có, quyền collection, preflight, retry/cancellation/cleanup và invalidation. Không xóa các lớp bảo vệ này chỉ vì index đang rỗng.
- Không gỡ adapter legacy hoặc sửa API hiện có. Nếu cần triển khai trên target khác có dữ liệu, phải xác nhận phạm vi riêng; quyền reset local không bao hàm project/production khác.

### Nghiệm thu trong phạm vi hiện tại

Test force, same fingerprint skip, changed fingerprint reprocess, task snapshot/version, read-only/invalid vector fail trước delete, retry sau partial upsert, cancel và generation update sau mutation/publish. Giữ kiểm thử schema/migration đã có. Không đánh dấu rollback drill/canary là đã thực hiện.

## 13. Đề xuất 10 — Kiểm thử kỹ thuật và smoke hệ thống, không triển khai evaluator

**Ưu tiên:** kiểm thử theo từng thay đổi P0/P1. Unit/integration/regression do implementation thực hiện; smoke model/provider/video thật do người dùng chạy. Evaluator và benchmark retrieval đã bỏ khỏi phạm vi theo mục 1.6.

### 13.1. Bộ test hiện có cần mở rộng và test cần tạo mới

| File hiện có hoặc cần tạo | Nội dung |
| --- | --- |
| `tests/unit/pipelines/test_pipeline_stages.py` | Timeline, dedup per-scene, hybrid pooling, payload/ID |
| `tests/unit/pipelines/test_full_video_media.py` | Chọn đúng derivative representative, một playback/video, cleanup |
| `tests/integration/pipelines/test_orchestrator_contract.py` | Thứ tự mới, version, ownership, persist failure; đây hiện là contract test dùng fake deps, không thay thế integration DB/Qdrant thật |
| `tests/unit/test_catalog.py`, `test_search_engine.py`, `test_search_points.py` | Schema v2/legacy, polarity/evidence, filter, grouping và candidate cache |
| `tests/unit/test_search_index.py` | Dimension theo name, preflight/read-only và replace |
| `tests/unit/test_ingestion_api.py`, `test_ingestion_task.py` | force/version/config snapshot/cancellation |
| `tests/unit/test_caption_refresh.py` | Status mới, không ghi đè scene evidence, cleanup khi lỗi/cancel |
| `tests/unit/test_qwen_embedding.py`, encoder/API tests liên quan | Ảnh/text local/remote, norm/dimension/finite/count |
| `tests/unit/test_config_video.py`, `test_search_schema.py` | Flags, validation, field optional và legacy behavior |

Thêm test selector, scene metadata và scene builder riêng nếu tách module; không nhồi mọi case vào một test file lớn. Có fixture và stub deterministic, không yêu cầu tải model cho unit tests.

### 13.2. Evaluator ngoài phạm vi

Không triển khai ResultRef mới, phép chấm scene/event/thumbnail, collection isolation phục vụ evaluator, temporal matching hoặc nguồn nhãn. Không sửa/xóa code và test evaluator cũ chỉ để làm regression pass. Những test đã có có thể chạy trong suite regression, không gọi đó là triển khai evaluator mới.

### 13.3. Kiểm tra trên hệ thống chạy thật

Người dùng kiểm tra ingestion hoàn tất, thumbnail/privacy/playback, search và thời gian/RAM/VRAM quan sát được bằng video thực. Không cần nhãn để smoke chức năng; kết quả này chưa chứng minh Recall/nDCG hoặc chất lượng tăng. Không triển khai benchmark A/B, calibration search floor hoặc duration-weighted pooling.

### 13.4. Lệnh kiểm chứng dự kiến khi triển khai

Chạy từ `app/` bằng Python môi trường project có dependency `[dev,media]`; model tests dùng stub trừ smoke inference thật. Trên Windows dùng interpreter `.venv/Scripts/python.exe` tương ứng; Makefile hiện ưu tiên layout Linux `.venv/bin/python`. Không dùng `python` PATH nếu nó là 3.9: project yêu cầu >=3.11.

```bash
python -m pytest tests/unit/pipelines tests/integration/pipelines/test_orchestrator_contract.py
python -m pytest tests/unit/test_catalog.py tests/unit/test_search_engine.py tests/unit/test_search_points.py tests/unit/test_search_index.py
python -m pytest tests/unit/test_ingestion_api.py tests/unit/test_ingestion_task.py
python -m ruff check api core db eval infrastructure ml pipelines repositories schemas search services worker tests
python -m ruff format --check api core db eval infrastructure ml pipelines repositories schemas search services worker tests
```

Sau focused checks, chạy suite backend đầy đủ một lần khi các thay đổi tích hợp xong. Nếu sửa frontend: `npm --prefix frontend test`, `npm --prefix frontend run lint`, `npm --prefix frontend run build` từ repo root. Migration upgrade/downgrade thử trên DB canary; smoke thật MinIO/Qdrant/Postgres phải có báo riêng, không dùng fake contract test để tuyên bố pass hạ tầng.

Các test mới như `tests/unit/test_caption_refresh.py`, selector và scene evidence được thêm vào focused command khi file đã được tạo. Chạy thêm test payload indexes và API media/export hiện có (`tests/unit/test_qdrant_payload_indexes.py`, `tests/api/test_media_endpoint.py`, `tests/api/test_admin_datasets_api.py`) khi sửa các hợp đồng tương ứng.

Không chạy CLI evaluator hoặc benchmark retrieval trong phạm vi hiện tại. Hướng dẫn smoke thao tác thực tế ở mục 20.

## 14. Thứ tự triển khai và cổng nghiệm thu

| Pha | Công việc | Điều kiện hoàn thành |
| --- | --- | --- |
| P0-A | Snapshot baseline, fixture timeline; hợp đồng data/version; đề xuất 1 và 8; điều phối builder trước dedup theo xác nhận 1.4 | Không vượt max, không sinh metadata giả; legacy vẫn đọc được |
| P0-B | Vector validation ảnh/text; preflight trước delete; skeleton fingerprint/migration | Invalid vector/read-only bị chặn trước khi mất dữ liệu cũ |
| P1-A | Builder trước dedup, ownership/batching, SigLIP all-sample/Qwen retained | Test ordering/cleanup/pooling và resource bound pass |
| P1-B | Representative schema + medoid không quality filter + thumbnail/API/export mapping | Thumbnail/frame/time khớp, playback seek đúng scene start; thiếu derivative fail-closed |
| P1-C | Content-aware builder và ngưỡng thử nghiệm có comment theo 1.6 | Boundary invariants và local config pass; không nhận là đã calibration |
| P1-D | Multi-frame VLM + evidence resolver/filter/refresh | Không co-occurrence giả; catalog và ANN cache path nhất quán; budget đo được |
| P2-A | Ngoài phạm vi theo 1.6: evaluator/benchmark retrieval | Đã loại khỏi phạm vi, không đánh dấu hoàn thành nghiệm thu |
| P2-B | Ngoài phạm vi theo 1.6: chuyển đổi/backup/rollback dữ liệu cũ | Local đã reset ở mục 19; không gọi reset là rollback drill |
| P2-C | Ngoài phạm vi: rollout batch vào target có dữ liệu | Người dùng chạy ingest mới; target khác cần xác nhận riêng |

Mỗi PR chứa một thay đổi quan sát được và test tương ứng; không gộp content boundary, weighted pooling và metadata mới rồi chỉ so một điểm retrieval tổng hợp. Có thể điều chỉnh thứ tự PR do dependency, nhưng không bật feature cần schema/adapter chưa deploy.

## 15. Các điểm còn cần dữ liệu hoặc quyết định ở thời điểm triển khai

Các lựa chọn kiến trúc D1–D4 đã chốt, không cần hỏi lại. Các mục dưới đây không bị coi là đã có câu trả lời từ workspace:

| Mục | Cách xử lý đã đề nghị |
| --- | --- |
| Content-aware threshold | Dùng heuristic đã chốt ở 1.6 cho local; người dùng điều chỉnh sau smoke; không nhận đã calibration |
| VLM novelty threshold | Default một frame; nhiều frame vẫn yêu cầu cấu hình novelty tường minh; không tự đặt giá trị |
| Quality threshold | Bỏ chức năng quality filter theo 1.6 |
| Ngưỡng chấp nhận regression và mức tăng chi phí | Đề xuất lập budget theo số liệu baseline; trình kết quả cụ thể trước rollout, không tự cam kết phần trăm cải thiện |
| Corpus/nhãn holdout và canary | Không phải điều kiện cho code chức năng trong phạm vi 1.6; không triển khai evaluator/canary |
| Có chấp nhận cửa sổ video tạm mất search khi in-place reindex không | Đã chốt: chấp nhận tạm gián đoạn từng video, canary trước rồi batch nhỏ có snapshot/rollback; không tự thực thi trên dữ liệu thật |
| Nghĩa truy vấn nhiều điều kiện | D4 đã chọn bằng chứng cùng frame cho nhóm cần đồng thời; nếu muốn “xuất hiện ở bất kỳ lúc nào trong cùng scene” như mode riêng thì hỏi trước khi bổ sung product semantics |
| Retention backup/media cũ, thời điểm chuyển live | Chốt bằng inventory và dung lượng thực; không tự xóa artifact cũ trong giai đoạn xây feature |

## 16. Checklist theo phạm vi hiện tại (mục 1.6)

Checkbox thể hiện yêu cầu còn hiệu lực; phần đã bỏ khỏi phạm vi không được diễn giải thành hoàn thành yêu cầu gốc. Mục 17–19 là lịch sử và không ghi đè trạng thái hiện tại.

- [x] 1. Timeline/coverage half-open, EOF/gap/max 5 giây được kiểm thử.
- [x] 2. Scene Builder trước dedup, dedup per-scene, ownership ảnh/batch bounded.
- [x] 3. Content-aware confirmation/buffer, time baseline; ngưỡng local thử nghiệm có cấu hình/comment và test. Calibration đã hoãn, không coi heuristic là ngưỡng đo được.
- [x] 4. SigLIP all-sample, Qwen retained; ảnh/text cùng contract vector (unit/contract; inference thật chưa xác nhận).
- [x] 5. Representative riêng, DB/Qdrant/API/export thống nhất scene start và thumbnail time.
- [x] 6. Medoid deterministic, thumbnail verified, fail-closed khi thiếu derivative. Quality filter đã loại khỏi phạm vi và khỏi code/config.
- [x] 7. Tối đa 3 VLM frame, evidence có timestamp; search/refresh nhất quán (kiểm thử chức năng; provider thật chưa xác nhận).
- [x] 8. Unknown/provenance; không có attribute/absence tưởng tượng.
- [x] 9. Fingerprint/snapshot cấu hình, migration/preflight/retry/cleanup/invalidation có kiểm thử; dữ liệu local cũ đã reset. Không triển khai backup/reindex/rollback dữ liệu cũ hoặc rollout P2.
- [ ] 10. Kiểm thử code bản chốt đã pass: 591 test regression, focused 77 test; integration server opt-in và smoke hệ thống/model/provider/video thật chưa chạy lại trong lượt này. Người dùng chạy smoke, chưa có kết quả. Evaluator/benchmark retrieval ngoài phạm vi.

**Đã bỏ khỏi phạm vi:** quality filter/calibration quality; evaluator, benchmark A/B retrieval và sửa evaluator; công cụ chuyển đổi/backup/rollback dữ liệu cũ và canary/batch rollout. **Còn cần người dùng chạy:** build/recreate local với code/config mới và smoke ingestion/search/media trên video thực. Không đánh dấu toàn bộ kế hoạch đã nghiệm thu chỉ từ code tests.

## 17. Báo cáo triển khai và bàn giao P0–P1-B (22/11/2026)

### 17.1. Phạm vi bàn giao đã được xác nhận

Người dùng đã xác nhận chưa có video/nhãn calibration và yêu cầu bàn giao P0–P1-B trước. P1-C, P1-D, P2-A/B/C **chưa triển khai/nghiệm thu** trong lần bàn giao này. Không đánh dấu toàn bộ kế hoạch hoàn thành.

Baseline repository để đối chiếu: `fc89c8ede612f01593b73029f0d1eed7c4f7384a`. Code được giữ trong working tree, chưa commit/deploy. Các thay đổi có sẵn ở root `Makefile`, `docker-compose.local.yml`, file CPU compose và hướng dẫn chạy của người dùng được giữ nguyên.

### 17.2. Trạng thái từng pha

| Pha | Đã triển khai | Đã kiểm chứng | Chưa thực hiện/giới hạn |
| --- | --- | --- | --- |
| P0-A | Timeline dùng chung với playback; probe/end source; coverage half-open có lookahead; cắt max 5 s; scene trước dedup; fallback unknown/provenance và validation metadata | Bộ P0-A 52 test pass; VFR/PTS không zero qua PyAV thật, EOF ngắn, privacy gap, timeline repair, legacy, unknown không trở thành positive/absent | Chưa đánh giá retrieval trên corpus thực |
| P0-B | Validation mọi vector ảnh/text; bỏ fallback Qwen sang SigLIP; fingerprint/snapshot từ API đến worker/task status/DB/payload; từ chối job cũ thiếu snapshot; migration nullable; preflight schema/index/vector/ownership trước thay dữ liệu; cleanup do đúng owner thực hiện | Bộ P0-B 80 test pass tại cổng pha; upgrade → downgrade → upgrade trên Postgres test; JSON snapshot và representative round-trip; Qdrant preflight giữ point cũ khi vector invalid | Không migrate DB ứng dụng, không reindex dữ liệu cũ, chưa có rollback drill dữ liệu thực của P2 |
| P1-A | Iterator SigLIP theo batch và scene; dedup per-scene; SigLIP sum trước dedup; Qwen chỉ retained; stage thumbnail trước khi đóng ảnh; đóng cả sample lookahead khi lỗi | Bộ pha 35 test pass; test phân biệt mean toàn sample với retained; video tổng hợp 100 frame có số ảnh nguồn mở bị chặn bởi batch + scene + lookahead; cleanup khi encoder lỗi | Chưa benchmark RSS/VRAM/tốc độ trên video production; metadata/vector output vẫn tăng theo số scene, không khẳng định toàn bộ RAM là hằng số |
| P1-B | Medoid SigLIP; middle baseline; quality filter opt-in có yêu cầu threshold/version; giữ derivative đại diện bị dedup mà không đưa nó vào Qwen; DB/Qdrant/API/export tách frame/time thumbnail và scene span; refresh hiểu timestamp đại diện | Bộ kiểm tra 109 test pass trước lượt guard cuối; kiểm tra medoid khác middle, tie deterministic, quality fallback, index/time zero, legacy/API seek, media/export; representative qua DB/Qdrant thật | Quality chỉ kiểm tra bằng fixture tổng hợp, chưa calibration; content-aware và multi-frame VLM chưa có trong runtime |

Các số 52/80/35/109 là kết quả tại cổng từng pha, không cộng chúng thành tổng test độc lập vì có test chạy lặp để kiểm tra regression. Lượt focused cuối hiện pass **125 test**, gồm hai integration test trên dịch vụ thật tách biệt.

### 17.3. File thay đổi và mục đích

- Timeline/coverage: `pipelines/ingestion/timeline.py` mới, `video_reader.py`, `playback_encoder.py`, `sampler.py`, `scene_builder.py`. Giữ PTS nguồn và quy tắc repair hiện tại của playback; `iter_scenes` có wrapper `build_scenes` cho caller cần list.
- Điều phối/bộ nhớ/pooling: `pipelines/ingestion/orchestrator.py`, `embedder.py`, `deduplicator.py`, `common/types.py`. Xử lý theo scene, đóng ảnh sớm, bảo vệ representative, lưu tổng SigLIP từ toàn sample và không encode lại ảnh đã có vector.
- Metadata: `pipelines/common/metadata.py` mới, `metadata_extractor.py`, `indexer.py`, `search/catalog.py`, `services/caption_refresh.py`. Unknown có provenance; JSON/enum/polarity được kiểm tra; không phát sinh default car/road/day/clear/absent rain-night; bổ sung trạng thái/counter enrichment trong kết quả ingestion.
- Vector contract/preflight: `ml/vectors.py` mới, `ml/encoder.py`, `ml/qwen_encoder.py`, `search/index.py`, `repositories/corpus.py`. Kiểm tra count/dimension/finite/norm từng hàng; epsilon norm lấy từ độ chính xác float Python, không phải ngưỡng retrieval/calibration; kiểm tra target trước delete. Không xóa Qdrant cũ khi thao tác delete DB chưa thành công.
- Identity/schema: `core/ingestion.py` mới, `core/config.py`, `db/models/corpus.py`, `db/models/ingestion_task.py`, `repositories/task_status.py`, `schemas/task.py`, `api/v1/ingestion.py`, `worker/tasks/ingestion.py`. Whitelist snapshot không chứa credential, fingerprint SHA-256 canonical, cùng version `scene-ingestion-v2`.
- Migration: `db/migrations/versions/20261122_0009_scene_ingestion_identity.py`, kế tiếp head `20260831_0008`. Thêm cột nullable cho identity/representative/thumbnail; không tự backfill medoid hoặc sửa dữ liệu legacy.
- Representative/media/API: `pipelines/ingestion/keyframe_selector.py` mới, `preview_generator.py`, `schemas/search.py`, `api/v1/search.py`, `services/datasets.py`, `infrastructure/qdrant.py`. `video_second` và `ts_start_s` vẫn là scene start; thời điểm/index ảnh đại diện có trường riêng. Frontend seek hiện tại không cần thay đổi.
- Cấu hình mẫu: `app/.env.example` ghi rõ medoid/middle và quality disabled; mọi threshold quality chỉ là placeholder comment, không có giá trị mặc định được tự đặt. Không sửa `.env` đang dùng, FPS mặc định hoặc cấu hình production.
- Tests: thêm `test_scene_timeline.py`, `test_unknown_metadata.py`, `test_scene_pooling.py`, `test_keyframe_selector.py`, `test_vector_contract.py`, `test_ingestion_identity.py`, `test_ingestion_infrastructure.py`; mở rộng contract/orchestrator và test liên quan. Cập nhật fixture dimension/DB columns/fake ownership theo contract mới, không xóa test để che lỗi.

Đường dẫn trong danh sách trên tính từ `app/`, ngoại trừ `app/.env.example` và migration đã ghi đầy đủ theo cấu trúc tương ứng.

### 17.4. Môi trường và bằng chứng kiểm chứng

- Tạo `app/.venv` Python 3.12, cài đúng dependency khai báo `.[dev,media]`; không thêm dependency vào manifest/lockfile, không tải model mới.
- Windows sandbox không tạo được socket nội bộ cho asyncio; các test async chạy ngoài sandbox theo quyền đã được cấp. `fcntl` của bulk ingest chỉ có trên Linux, nên regression đầy đủ dùng container Python Linux với source mount read-only, loại `.env`, `.git`, `.venv`, node_modules và data trước khi copy vào filesystem tạm.
- Tạo riêng Postgres `postgres:16-alpine` và Qdrant `qdrant/qdrant:v1.13.6` với cổng localhost ngẫu nhiên, không mount volume dữ liệu hiện có. Integration test từ chối endpoint không phải localhost và DB không đúng tên test; collection Qdrant có UUID riêng và được cleanup trong test.
- Migration đã chạy trên DB `scenesearch_upgrade_test`, không phải database ứng dụng. Đã xác minh head Alembic mới là `20261122_0009`.
- Ruff check toàn backend pass; format check toàn backend pass (188 file được kiểm tra tại lượt cuối). `git diff --check` pass.
- `python -X utf8 -m eval.cli --dry-run` pass, in 28 case; đây chỉ là kiểm tra harness, không phải benchmark. UTF-8 là flag của lệnh chạy trên Windows, không sửa evaluator để che lỗi.
- Model inference thật và VLM provider thật chưa được kiểm chứng; unit/contract dùng output stub có dimension hợp lệ. Test media dùng PyAV/FFmpeg thật; test DB/Qdrant thật được báo tách với contract fake storage.

Kết quả regression Linux trên **bản code chốt: 533 pass, 4 skip, 2 warning**. Hai skip do ML extra chưa cài, hai skip do container regression không nhận endpoint hạ tầng opt-in; hai integration tương ứng đã chạy thật trong lượt focused **125 test pass**. Hai warning fixture RLHF về `AsyncMock` nằm ngoài phạm vi và chưa sửa. Không cộng số focused vào số regression vì có các test chạy lại.

Hai container Postgres/Qdrant test đã được xác minh đúng ID do phiên làm việc tạo, sau đó dừng và tự xóa qua `--rm`. Container regression cũng tự xóa sau khi kết thúc. Không xóa volume dữ liệu ứng dụng, không chạy migration hoặc reindex trên hệ thống hiện có.

### 17.5. Điều kiện sử dụng và phần còn lại

1. Chưa chạy migration trên DB ứng dụng. Khi triển khai thật phải áp dụng migration được duyệt trước khi chạy API/worker mới; không dùng kết quả test container để kết luận DB hiện có đã được nâng cấp.
2. Job đã enqueue theo phiên bản cũ không có snapshot sẽ bị từ chối với lỗi cấu hình rõ ràng và cần enqueue lại qua API mới. Đổi cấu hình sau enqueue cũng bị từ chối, không âm thầm chạy với cấu hình khác.
3. Dữ liệu scene/vector cũ chưa được cập nhật. Không tự chạy reindex; fingerprint null ở dữ liệu legacy không được coi là output v2 đã có sẵn.
4. Runtime vẫn chia scene theo thời gian, tối đa 5 s. Content-aware/boundary confirmation/calibration thuộc P1-C chưa triển khai.
5. Runtime VLM vẫn phân tích một frame đại diện. Tối đa ba frame, evidence nhiều thời điểm, hậu kiểm cùng observation và bảo vệ refresh đa-frame thuộc P1-D chưa triển khai.
6. Medoid được triển khai và có thể dùng; quality filter mặc định tắt, bật khi thiếu threshold/version sẽ báo lỗi cấu hình. Các threshold fixture test không được sao chép sang cấu hình sử dụng thật.
7. Chưa đo Recall/nDCG/event coverage/thumbnail relevance trên dữ liệu độc lập; chưa hiệu chỉnh floor, chưa canary reindex/rollback drill/rollout. Không khẳng định retrieval tốt hơn hay tốc độ nhanh hơn.
8. Cần nguồn video và nhãn boundary/event/thumbnail độc lập, split calibration/holdout theo video, trước khi tiếp tục các cổng còn lại. Người dùng đã chọn bàn giao đến P1-B thay vì tự giả định đã có dữ liệu.


## 18. Tiếp tục P1-C/P1-D: triển khai chức năng, hoãn calibration và P2

### 18.1. Phạm vi và trạng thái nghiệm thu

Áp dụng xác nhận cập nhật tại mục 1.5. Mục 17 giữ nguyên như báo cáo lịch sử của lần bàn giao P0–P1-B. Không dùng kết quả test tổng hợp để coi ngưỡng đã calibration hoặc khẳng định chất lượng retrieval tăng.

| Pha | Đã triển khai | Phần kiểm chứng chức năng | Chưa thực hiện |
| --- | --- | --- | --- |
| P1-C | Mode `content_time` opt-in; local/global candidate; centroid không nhận pending trước quyết định; xác nhận theo số sample và thời gian; min-duration mềm global-only; xử lý flash/EOF/gap/hard max; reason/distances ghi payload; cấu hình và fingerprint | Fixture hard cut ở 1/5 fps, gradual drift, jitter nhẹ, flash một sample, EOF/max/gap đang pending, frame membership và tổng SigLIP; time default; cấu hình thiếu bị từ chối | Calibration/holdout, boundary/event recall và false split trên video thật; chưa đạt toàn bộ cổng P1-C của mục 14 |
| P1-D | Candidate tối đa 3, representative trước và farthest-point; dedup quyết định trước khi đóng ảnh; VLM budget có cấu hình và đếm HTTP request; metadata v2 có observation/provenance; aggregate caption có timestamp; resolver/filter dùng cùng policy; refresh thumbnail-only; generation invalidation có TTL fallback | HTTP transport giả lập kiểm tra thành công 1/3 và 3/3, lỗi 3/3, missing key, timeout/429/JSON lỗi, privacy và concurrency/attempts; AND cùng observation, counts/unknown/exclude; catalog và candidate cache; Qdrant local round-trip; ảnh đóng ở lỗi/cancel | Provider/model inference thật, token/cost/latency/RAM/VRAM thực tế; chưa có đánh giá độc lập về chất lượng multi-frame hoặc config nên bật |
| P2-A/B/C | Chưa thực hiện | Không dùng dry-run/local fixture làm benchmark/canary | Evaluation/A-B/calibration, canary thực và reconcile/rollback, batch rollout sau phê duyệt |

### 18.2. File liên quan và lý do thay đổi

Các đường dẫn dưới đây tính từ `app/`:

- `core/config.py`, `core/ingestion.py`, `.env.example`: khai báo cấu hình đã xác nhận; schema metadata fingerprint là 2; snapshot giữ toàn bộ cấu hình video resolved. `.env` thực không thay đổi. Local/global/min/confirmation và novelty không có giá trị tự đặt; default vẫn time, VLM một frame, quality disabled.
- `pipelines/ingestion/scene_builder.py`: content candidate/confirmation và buffer theo thứ tự timeline; sum chỉ thuộc đúng scene; gap/hard max ưu tiên. `indexer.py` ghi reason/distances phục vụ debug sau persistence.
- `pipelines/ingestion/vlm_candidates.py` mới, `keyframe_selector.py`, `deduplicator.py`, `orchestrator.py`, `common/types.py`: tái sử dụng quality; chọn từ toàn sample còn mở; giữ candidate/representative riêng với retained Qwen. `close_dropped=False` chỉ tách quyết định và ownership ảnh nội bộ, không phải cấu hình runtime mới. Metrics tách scenes success/partial/failed/not_configured, selected frame count và HTTP request count.
- `pipelines/ingestion/metadata_extractor.py`, `scene_metadata.py` mới: giữ provider/prompt, giới hạn inference theo cấu hình; chỉ gửi derivative verified; aggregate observations sau khi validation. Không thêm HTTP call viết caption tổng hợp. Canonical conflicts bị đánh dấu failed/unknown, không đưa evidence mâu thuẫn vào search; detector evidence thực vẫn được giữ.
- `schemas/scene_evidence.py` mới: schema v2 trong metadata JSON, không thêm migration. Có frame/time/source/status/model/prompt, attrs, positive/explicit negative, detector object counts, representative reference, sampled/candidate/succeeded counts và selected-instant coverage. `complete_for_selected_frames` không mang nghĩa quan sát mọi thời điểm video.
- `pipelines/ingestion/embedder.py`, `indexer.py`: bổ sung provenance pooling per tower (method/source/input count/model version), không đổi phép pooling. Sample count chưa biết ở caller ngoài pipeline giữ null thay vì giả định.
- `search/query.py`, `catalog.py`, `scene_evidence.py` mới, `engine.py`: tái sử dụng cùng bảng ánh xạ weather/time hiện có; giữ evidence trong adapter; v2 không đọc lại caption tổng hợp để suy diễn đồng thời. Required/object/count được hậu kiểm chung trên một observation. Unknown không được confirmed hay denied; scene-level absence để rỗng. Resolver legacy giữ nguyên. Khi phạm vi có v2, cả nhánh trả rỗng và có kết quả đều không báo exhaustive; degraded vẫn chỉ lỗi retrieval. ANN, RRF, tower/ranking/grouping không đổi.
- `services/caption_refresh.py`: chỉ thay observation representative, giữ observations khác và detector evidence; tổng hợp lại summary, ghi `refresh_scope=thumbnail_only`. Không lấy một thumbnail thay cả scene và không giả lập việc phục hồi đủ ba ảnh. Cleanup ảnh ở cả lỗi và cancellation; invalidation sau batch đã ghi trước khi progress callback có thể thất bại.
- `services/catalog_generation.py` mới, `search/catalog.py`, `search/index.py`, `orchestrator.py`: dùng chung generation key; báo mutation sau delete/upsert/publish/refresh. Redis lỗi được log và dùng TTL hiện có; không cleanup dữ liệu đã publish chỉ vì invalidation lỗi.
- Tests mới: `test_content_scene_builder.py`, `test_scene_metadata.py`, `test_scene_evidence.py`, `test_caption_refresh.py`, `test_scene_evidence_roundtrip.py`. Mở rộng `test_orchestrator_contract.py`, `test_scene_pooling.py`, `test_search_index.py` cho vòng đời candidate, pooling provenance và generation isolation. Test dùng transport/fake dependencies đúng tầng, không thêm mock vào production code.

### 18.3. Giới hạn sử dụng

- Chưa chọn giá trị calibration cho bất kỳ cosine/novelty/quality threshold nào; không sao chép các giá trị fixture test sang cấu hình triển khai. Muốn thử `content_time` hoặc nhiều frame phải cung cấp cấu hình tường minh và coi đó là thử nghiệm chưa đánh giá.
- Weather/time/scene summary chỉ giữ known value khi các observation thành công nhất quán; mâu thuẫn giữ unknown và chi tiết ở evidence. Top-level unknown dùng null, để refresh loại giá trị known cũ khỏi filter; không gán clear/day mặc định.
- Scene positives là union broad cho pushdown; không chứng minh co-occurrence. Các object count theo lớp là max giữa observation, chỉ dùng broad summary; hậu kiểm xét count cùng frame với required/object constraints.
- Không có detector/tracker mới; VLM qualitative traffic không biến thành số lượng object chính xác. Không thêm temporal parser hoặc chứng minh quan hệ/hành động từ hai frame khác nhau.
- Full reingest mới tái tạo được multi-frame evidence khi chỉ còn lưu thumbnail. Job/snapshot từ bản cũ không được âm thầm chạy như schema mới.
- Không migrate database ứng dụng, không xử lý/reindex video ở `D:\User_Files\datadoan`, không thay collection live hoặc xóa dữ liệu hiện có. Không thêm dependency/model/API/migration; không thay đầu vào embedding hoặc sampling FPS.
- Calibration/evaluation/canary/rollback/rollout tiếp tục chờ dữ liệu và phê duyệt riêng; chưa đánh dấu toàn bộ kế hoạch hoàn thành.


### 18.4. Kết quả kiểm thử và cổng bàn giao

- P1-C tại cổng trước khi bắt đầu P1-D: **43 pass**, gồm content scene builder, timeline, pooling, config, identity và orchestrator contract. Sau đó bổ sung ca jitter và provenance; các ca này nằm trong kiểm tra cuối.
- Regression Linux lần đầu: **576 pass, 4 skip, 2 warning**. Sau bổ sung jitter và provenance, regression Linux lần hai: **577 pass, 4 skip, 2 warning**, pytest 13.77 giây (không tính cài dependency). Đây là bộ toàn backend trong container Python 3.12, source mount chỉ đọc, copy không có `.env` hoặc data.
- Quyết định `exhaustive` được xác nhận sau regression Linux lần hai. Đã bổ sung guard cả hai nhánh return và 5 test phạm vi/empty/success/legacy. Kiểm tra focused trên **bản code cuối sau quyết định này: 124 pass**, pytest 26.99 giây. Gồm `test_search_engine.py`, `test_scene_evidence.py`, `test_caption_refresh.py`, `test_scene_metadata.py`, `test_content_scene_builder.py`, `test_scene_pooling.py`, `test_search_index.py`, `test_orchestrator_contract.py`, `test_scene_evidence_roundtrip.py`. Không gọi số 577 là kết quả full-suite sau thay đổi exhaustive; không cộng các lượt test với nhau.
- Bốn skip của regression: hai test ML extra chưa cài, hai test Postgres/Qdrant server cần endpoint opt-in. Hai integration hạ tầng server ở mục 17 không chạy lại trong lượt này; không có migration mới. Test Qdrant bổ sung của P1-D dùng engine local `:memory:`, kiểm tra serialization/named vectors/filter/postfilter, không thay thế canary hoặc test dịch vụ production.
- Hai warning regression vẫn ở fixture `tests/unit/test_rlhf_feedback.py` (`AsyncMock` của `session.add` chưa await); không sửa phần ngoài phạm vi này. Cảnh báo pip root trong container là cảnh báo môi trường tạm, không phải kết quả benchmark.
- Ruff check toàn backend pass; format check pass; `git diff --check` pass. Không thay dependency manifest/lockfile. Hai container Python regression tự xóa bằng `--rm` sau khi kết thúc, không mount dữ liệu hiện có để ghi.
- Test VLM dùng HTTP transport giả lập, không gọi provider/model thật. Test media/ingestion hiện có vẫn pass; kiểm tra ảnh candidate sống đến VLM và đóng sau scene/lỗi/cancel. Không có kết quả đo RSS/VRAM/throughput/token/cost trên video thật.

**Cổng bàn giao:** P1-C/P1-D đã triển khai và kiểm chứng chức năng trong phạm vi cập nhật tại mục 1.5. Cổng calibration của P1-C và nghiệm thu chất lượng/chi phí trên dữ liệu thật vẫn chưa đạt vì chưa thực hiện. P2-A/B/C chưa thực hiện. Không coi toàn bộ kế hoạch đã hoàn thành; không bật content-aware/multi-frame/quality trên môi trường hiện có.


## 19. Dọn dữ liệu ingestion local theo yêu cầu người dùng (23/11/2026)

Người dùng yêu cầu xóa toàn bộ dữ liệu ingestion cũ để ingest lại từ đầu. Đã xác định target bằng nhãn Compose và working directory: chỉ stack `scenesearch-local` thuộc workspace hiện tại. Stack `scenesearch-infra` thuộc project ở thư mục khác không nằm trong phạm vi.

### Phạm vi thực tế đã xóa và kiểm chứng

| Nơi lưu | Trước | Sau |
| --- | --- | --- |
| Postgres `scenesearch`: videos | 3 | 0 |
| Postgres: segments | 7 | 0 |
| Postgres: ingestion_tasks | 4 | 0 |
| Postgres: frames/objects/attributes/behavior_events | 0 | 0 |
| Qdrant local: `scenes_local` | 7 point | 0 point |
| MinIO: `scenesearch-raw` | 3 bản video đã upload, 17.708.076 byte | 0 object |
| MinIO: `scenesearch-derived` | 10 thumbnail/playback, 6.019.110 byte | 0 object |
| MinIO: `scenesearch` | 0 object | 0 object |
| Redis cache task ingestion | 4 key | 0 key |
| Postgres: users | 1 | 1, giữ nguyên |

Preflight đã xác minh API/worker dừng, không có task active, hàng đợi ingestion/default/celery rỗng, không có unacked job; collection đúng target local, được cấu hình cho phép ghi, named vectors qwen 2048/siglip 768 và Cosine. Tất cả point/object đối chiếu thuộc ba video đã kiểm kê; bucket không bật versioning. Kiểm tra lại manifest trước thao tác xóa; xóa Postgres bằng transaction có guard số bản ghi, không truncate toàn DB hoặc dùng CASCADE toàn schema.

Giữ schema/Alembic state, collection/vector schema/payload indexes, bucket, tài khoản admin, Redis auth và broker bindings, Docker volumes và model caches. Đã tăng catalog generation sau cleanup. Không xóa file nguồn tại `D:\User_Files\datadoan`, không đụng project/stack khác. Không sửa ngưỡng hoặc quality filter trong thao tác dọn dữ liệu này.

Dữ liệu cũ được xóa theo yêu cầu, không tạo backup để phục hồi. Kết quả này là reset dữ liệu local, không phải nghiệm thu canary/rollback hoặc triển khai production của P2. Sau khi khởi động lại hệ thống, cần upload/ingest lại video để có dữ liệu search.


## 20. Bàn giao thay đổi phạm vi và cấu hình local (23/11/2026)

### 20.1. Đã triển khai

- `app/.env`, `app/.env.local.example`, `app/.env.example`: cấu hình `content_time` với local/global distance 0.10/0.15, min-duration mềm 2.0 giây, confirmation 0.4 giây. Comment giải thích phép đo, cách chỉnh và trạng thái chưa calibration. Code default vẫn `time`, threshold numeric trong code vẫn unset; cấu hình local cấp giá trị tường minh. Không thay FPS/dedup/VLM budget. `.env` có credential nên không in toàn file hoặc đưa vào báo cáo.
- `app/core/config.py`: bỏ toàn bộ field/validation quality filter; giữ validation segmentation và novelty hiện có. Không thêm cấu hình runtime, API, cột DB hoặc dependency.
- `app/pipelines/ingestion/keyframe_selector.py`: bỏ tính Laplacian/clipping và quality tie-break; chỉ medoid trong tập derivative verified, tie theo midpoint rồi timestamp/index, version `cosine-medoid-v2`. Thiếu derivative vẫn fail-closed; middle vẫn tương thích.
- `app/pipelines/ingestion/vlm_candidates.py`: bỏ quality gate; giữ representative/farthest-point/temporal tie/novelty, không tăng default candidate budget.
- `app/pipelines/ingestion/orchestrator.py`: đồng bộ signature selector sau khi bỏ tham số resize chỉ phục vụ quality; không đổi ownership ảnh, tập Qwen/SigLIP hoặc thứ tự pipeline.
- `app/core/ingestion.py`: snapshot bỏ field quality theo model config mới và ghi representative version mới; đổi fingerprint khi đổi ngưỡng, không giữ nhầm fingerprint cũ.
- Tests `test_content_scene_builder.py`, `test_config_video.py`, `test_keyframe_selector.py`, `test_scene_metadata.py`, `test_ingestion_identity.py`: kiểm tra bộ trial được duyệt, default time, config local, snapshot/fingerprint, dark/flat thumbnail và fail-closed. Thay test chất lượng của tính năng đã bỏ bằng test hành vi mới, không xóa test để che lỗi.
- Tài liệu được đồng bộ theo 1.6: quality filter/evaluator và công cụ chuyển đổi/backup/rollback dữ liệu cũ không còn là yêu cầu đang chờ triển khai. Mục 19 vẫn là bằng chứng reset local; không gọi reset là canary/rollback nghiệm thu.

### 20.2. Kiểm chứng và giới hạn

- Cổng cấu hình content-aware trước khi bỏ quality: **26 pass**, gồm fixture hard cut ở 1/5 fps và gradual drift dùng đúng cấu hình local mẫu.
- Sau khi bỏ quality: **77 pass** trong focused suite (selector, scene metadata, config, content builder, pooling, identity, orchestrator contract, media, scene evidence). Các test async Windows chạy ngoài sandbox; chạy từ repo root để không đọc `.env` local chứa credential.
- Đã đọc settings từ `app/.env` và kiểm tra riêng các field được phép in: content_time, 0.10/0.15/2.0/0.4, FPS 1.0, dedup 0.98, VLM 1, medoid, calibration version unset; không còn field quality filter. JPEG compression quality giữ 80.
- Regression Linux trên bản code chốt: **591 pass, 4 skip, 2 warning**, pytest 14.85 giây (không tính chuẩn bị dependency). Hai skip là test ML extra chưa cài; hai skip là integration Postgres/Qdrant cần endpoint opt-in. Test local Qdrant/media/contract vẫn chạy, không gọi đây là integration server hoặc inference model thật.
- Hai warning vẫn thuộc fixture RLHF (`AsyncMock` của `session.add` chưa await), ngoài phạm vi nên không sửa. Không cộng số focused và regression vì có test trùng giữa các lượt. Không sửa code/test evaluator; test evaluator cũ chỉ được chạy như phần regression hiện có.
- Ruff check và format check toàn backend pass (199 file); `git diff --check` pass. Container Python test chỉ mount source read-only, loại `.env`, data và cache trước khi copy; tự xóa sau khi kết thúc. Không thay dependency manifest/lockfile, không chạy migration vào DB ứng dụng hoặc ghi dữ liệu local đã reset.
- Model/provider inference thật và smoke hệ thống sau build/recreate chưa thực hiện. Không có số đo chất lượng, latency/RAM/VRAM hoặc tuyên bố ngưỡng tối ưu.

**Cổng bàn giao lần này:** ngưỡng trial/config local và việc loại quality filter đã triển khai, kiểm chứng bằng unit/contract/local integration/regression. Checklist 3/6/9 được diễn đạt theo phạm vi cập nhật; không ghi calibration/rollback/evaluator là đã nghiệm thu. Checklist 10 còn mở vì chạy thật chưa được thực hiện.

### 20.3. Người dùng chạy hệ thống thật

1. Từ repo root chạy `make local-up CPU=1` theo hướng dẫn local hiện có, rồi `make local-ps CPU=1`. Cần build/recreate để API và worker cùng nhận code/config mới; chỉ start container cũ sẽ dùng image/environment cũ. API startup áp dụng schema migration hiện có, không cần tạo migration mới trong lượt thay đổi này.
2. Giữ tài khoản admin đã có sau reset; không cần seed lại tài khoản. Mở trang Ingestion, chờ embedding service READY, upload một video ngắn và theo dõi task.
3. Kiểm tra ingestion completed, dữ liệu mới xuất hiện trong Postgres/Qdrant, mỗi scene tối đa 5 giây, named vectors qwen/siglip đúng contract. Metadata có schema_version 2 và representative reference; VLM success/failed/not_configured phản ánh đúng provider, không có API key thì unknown là dự kiến.
4. Mở thumbnail/playback: ảnh đã anonymize, ảnh đại diện cố định, seek theo scene start, representative timestamp nằm trong scene. Kiểm tra scene cuối ngắn/đổi cảnh nếu video có; không yêu cầu ảnh phải qua bộ lọc độ nét/clipping.
5. Thử search trên nội dung video vừa upload. Search ranking giữ nguyên; phạm vi chứa v2 không báo exhaustive. Kiểm tra kết quả/media hoạt động, không dùng smoke để khẳng định Recall/nDCG.
6. Khi cần điều chỉnh: sửa các `VIDEO_SCENE_*` trong `app/.env` theo comment và recreate API/worker cùng cấu hình trước enqueue job mới. Tăng boundary distance làm khó tạo candidate hơn; global distance còn ảnh hưởng pending consistency. Không sửa FPS/dedup/VLM budget để tránh thay nhiều yếu tố cùng lúc. Job snapshot cũ không được chạy âm thầm với cấu hình mới; enqueue lại khi cấu hình thay đổi.
7. Ghi lại lỗi thực tế, video/thời điểm lỗi, task status và số liệu runtime quan sát được nếu có; không cần bộ nhãn/evaluator để chạy smoke chức năng.

**Chưa thực hiện:** build/recreate stack local, ingest/search/provider thật và kiểm tra runtime bởi người dùng. Không tự khởi động model, tải video để ingest hoặc chạy batch rollout trong lượt sửa code này.
