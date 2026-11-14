"""Create a local, prediction-blind annotation review page. Reads Qdrant only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review-dir', default='review-oriented')
    parser.add_argument('--export-name', default='pilot.reviewed.jsonl')
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.labels.read_text(encoding='utf-8').splitlines() if line.strip()]
    videos = []
    seen = set()
    for row in rows:
        video_id = row['target_video_id']
        if video_id in seen:
            continue
        seen.add(video_id)
        payload = {'filter': {'must': [{'key': 'video_id', 'match': {'value': video_id}}]},
                   'limit': 1, 'with_payload': False, 'with_vector': False}
        request = Request('http://127.0.0.1:6333/collections/scenes_local/points/scroll',
                          data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=10) as response:
            points = json.load(response)['result']['points']
        if not points:
            raise ValueError('No legacy media locator for ' + video_id)
        videos.append({'video_id': video_id, 'preview_url': 'http://127.0.0.1:8000/api/v1/media/clip/' + str(points[0]['id']),
                       'review_sheet': args.review_dir.rstrip('/') + '/' + row['review_sheet']})
    template = Path(__file__).resolve().parents[1] / 'evaluation/review-template.html'
    notice = ('Các query là gợi ý chưa có nhãn. Hãy xem video đầy đủ, sửa query theo nội dung thực nếu cần, rồi chọn có/không và đánh dấu thời gian.'
              if any(row['pair_relation'] == 'unlabeled' for row in rows) else
              'Các khoảng thời gian có sẵn cần được kiểm tra bằng video đầy đủ. Trang không hiển thị dự đoán model.')
    if rows and all(row.get('label_status') == 'provisional_assistant_visual' for row in rows):
        positives = sum(row['pair_relation'] == 'positive' for row in rows)
        notice = (f'Bộ query được viết theo frame nguồn: {positives} câu có sự kiện quan sát được và '
                  f'{len(rows) - positives} câu đối chứng không thấy xuất hiện. Thời gian và quan hệ chỉ là gợi ý sơ bộ. '
                  'Hãy xem toàn bộ video, kiểm tra mọi lần xuất hiện và chỉnh ranh giới trước khi xác nhận. '
                  'Trang không hiển thị dự đoán model. Không nạp bản nháp của bộ query cũ.')
    notice += ' Có thể xuất bản nháp và nạp lại để tiếp tục; các nhãn chưa xác nhận không phải đáp án chuẩn.'
    data = json.dumps({'videos': videos, 'rows': rows, 'notice': notice, 'export_name': args.export_name}, ensure_ascii=False).replace('<', '\\u003c')
    args.output.write_text(template.read_text(encoding='utf-8').replace('__DATA__', data), encoding='utf-8')
    print(json.dumps({'review_page': str(args.output), 'videos': len(videos), 'pairs': len(rows)}))


if __name__ == '__main__':
    main()
