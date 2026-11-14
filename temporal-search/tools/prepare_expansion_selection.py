"""Select new videos for annotation independently of search/model outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ingestion-manifest', type=Path, required=True)
    parser.add_argument('--pilot-labels', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    pilot = [json.loads(line) for line in args.pilot_labels.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    old_ids = {row['target_video_id'] for row in pilot}
    old_prefixes = {Path(row['relative_source']).stem.split('-')[0] for row in pilot}
    data = json.loads(args.ingestion_manifest.read_text(encoding='utf-8'))['files']
    candidates = [(path, value) for path, value in sorted(data.items())
                  if value.get('status') == 'completed' and value['video_id'] not in old_ids
                  and Path(path).stem.split('-')[0] not in old_prefixes]
    random.Random(20261114).shuffle(candidates)
    selected = []
    seen_prefixes = set()
    for path, value in candidates:
        prefix = Path(path).stem.split('-')[0]
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        selected.append({'relative_source': path, 'video_id': value['video_id'], 'filename_prefix': prefix,
                         'split': 'validation' if len(selected) < 8 else 'test'})
        if len(selected) == 20:
            break
    if len(selected) != 20:
        raise ValueError('Not enough distinct source prefixes for expansion')
    if args.output.exists():
        raise ValueError('Preserve existing selection; choose a new output path')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selected, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'selected_videos': len(selected), 'seed': 20261114,
                      'selection': 'seeded completed-video sample, excluding pilot IDs/prefixes; prefix is not verified trip identity'}))


if __name__ == '__main__':
    main()
