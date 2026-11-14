"""Create deterministic, model-independent visual review sheets from raw videos."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import av
from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ingestion-manifest', type=Path, required=True)
    parser.add_argument('--raw-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=10)
    parser.add_argument('--selection', type=Path, help='Explicit source/video selection, instead of the first completed videos')
    args = parser.parse_args()
    records = json.loads(args.ingestion_manifest.read_text(encoding='utf-8'))['files']
    if args.selection:
        selection = json.loads(args.selection.read_text(encoding='utf-8'))
        selected = []
        for item in selection[:args.count]:
            value = records[item['relative_source']]
            if value.get('status') != 'completed' or value['video_id'] != item['video_id']:
                raise ValueError('Selection does not match the ingestion manifest')
            selected.append((item['relative_source'], value))
    else:
        selected = [(path, value) for path, value in sorted(records.items()) if value.get('status') == 'completed'][:args.count]
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
    except OSError:
        font = ImageFont.load_default()
    manifest = []
    for index, (relative, record) in enumerate(selected):
        source = (args.raw_root / relative).resolve()
        if args.raw_root.resolve() not in source.parents:
            raise ValueError('Source escaped raw root')
        output = args.output / record['video_id']
        output.mkdir(exist_ok=True)
        times = []
        frames = []
        with av.open(str(source)) as container:
            stream = container.streams.video[0]
            duration = float(stream.duration * stream.time_base) if stream.duration else container.duration / av.time_base
            targets = [float(value) for value in range(1, math.ceil(duration), 2) if value < duration]
            target_index = 0
            for frame in container.decode(stream):
                timestamp = float(frame.time or 0)
                if target_index >= len(targets):
                    break
                if timestamp < targets[target_index]:
                    continue
                image = frame.to_image().convert('RGB')
                rotation = getattr(frame, 'rotation', 0) or 0
                if not rotation and stream.metadata.get('rotate'):
                    rotation = -float(stream.metadata['rotate'])
                if rotation:
                    oriented = image.rotate(round(float(rotation) / 90) * 90, expand=True)
                    image.close()
                    image = oriented
                image.thumbnail((1280, 720))
                image.save(output / ('frame_%05.1f.jpg' % timestamp), quality=85)
                tile = image.copy()
                tile.thumbnail((320, 180))
                frames.append(tile)
                times.append(round(timestamp, 4))
                target_index += 1
        rows = math.ceil(len(frames) / 4)
        sheet = Image.new('RGB', (1280, rows * 204 + 44), '#12151b')
        draw = ImageDraw.Draw(sheet)
        draw.text((10, 8), '%02d %s | %s | %.3fs' % (index, source.name, record['video_id'], duration), font=font, fill='white')
        for position, (tile, timestamp) in enumerate(zip(frames, times)):
            x, y = (position % 4) * 320, 44 + (position // 4) * 204
            sheet.paste(tile, (x, y))
            draw.text((x + 6, y + 182), '%.3fs' % timestamp, font=font, fill='white')
        sheet_path = args.output / ('review_%02d.jpg' % index)
        sheet.save(sheet_path, quality=90)
        item = {'index': index, 'video_id': record['video_id'], 'relative_source': relative,
                'duration_s': round(duration, 6), 'review_timestamps_s': times,
                'review_sheet': sheet_path.name, 'frames_directory': record['video_id'],
                'review_status': 'unreviewed', 'label_source': None}
        manifest.append(item)
        print(json.dumps({'index': index, 'video_id': record['video_id'], 'duration_s': duration, 'frames': len(frames)}), flush=True)
    (args.output / 'videos.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
