"""Build editable, visually grounded requests; human review is still required."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def build_requests(selection, videos, observations):
    chosen = {row['video_id']: row for row in selection}
    observed = {row['video_id']: row for row in observations['videos']}
    if (len(videos) != 20 or len(observed) != 20 or len(chosen) != 20
            or set(observed) != set(chosen)
            or {video['video_id'] for video in videos} != set(chosen)):
        raise ValueError('This expansion requires the same 20 selected and visually inspected videos')
    rows = []
    for video in videos:
        observation = observed[video['video_id']]
        if observation['video_index'] != video['index']:
            raise ValueError('Video index does not match visual observation')
        items = observation['items']
        if len(items) != 5 or sum(bool(item['windows']) for item in items) != 4:
            raise ValueError('Each video requires four provisional positives and one negative control')
        for item in items:
            query, query_vi = item['query'].strip(), item['query_vi'].strip()
            if not query or not query_vi or not item['evidence']:
                raise ValueError('Queries need both translations and source-frame evidence')
            windows = item['windows']
            if any(len(pair) != 2 or not all(math.isfinite(value) for value in pair)
                   or not 0 <= pair[0] < pair[1] <= video['duration_s'] for pair in windows):
                raise ValueError('Provisional window lies outside the source video')
            timestamps = video['review_timestamps_s']
            evidence = [min(timestamps, key=lambda value: abs(value - target)) for target in item['evidence']]
            if any(abs(actual - target) > 0.2 for actual, target in zip(evidence, item['evidence'])):
                raise ValueError('Evidence timestamp does not correspond to an inspected frame')
            if any(not any(start <= timestamp < end for timestamp in evidence) for start, end in windows):
                raise ValueError('Each provisional positive window needs an inspected supporting frame')
            digest = hashlib.sha256((video['video_id'] + '\n' + query).encode('utf-8')).hexdigest()[:12]
            rows.append({
                'query_id': 'expansion-%02d-%s' % (video['index'], digest),
                'query': query, 'query_vi': query_vi, 'query_editable': True,
                'query_category': 'observed_event' if windows else 'easy_negative_control',
                'target_video_id': video['video_id'], 'relative_source': video['relative_source'],
                'duration_s': video['duration_s'], 'split': chosen[video['video_id']]['split'],
                'filename_prefix': chosen[video['video_id']]['filename_prefix'],
                'pair_relation': 'positive' if windows else 'negative_for_target_video',
                'relevant_windows': windows, 'human_verified': False,
                'label_status': 'provisional_assistant_visual', 'boundary_uncertainty_s': 2.0,
                'review_sheet': video['review_sheet'],
                'review_method': observations['curation_method'],
                'visual_evidence_timestamps_s': evidence,
                'source_curation_note': observation['note'],
                'curation_limitations': observations['limitations'],
                'corpus_relevance_exhaustive': False,
            })
    if len(rows) != 100 or len({row['query'].casefold() for row in rows}) != 100:
        raise ValueError('This expansion requires 100 distinct queries')
    if len({row['query_id'] for row in rows}) != 100:
        raise ValueError('Duplicate query identity')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--videos', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--observations', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'evaluation/expansion-observations.json')
    parser.add_argument('--replace', action='store_true', help='Replace the canonical requests explicitly')
    args = parser.parse_args()
    rows = build_requests(json.loads(args.selection.read_text(encoding='utf-8')),
                          json.loads(args.videos.read_text(encoding='utf-8')),
                          json.loads(args.observations.read_text(encoding='utf-8')))
    if args.output.exists() and not args.replace:
        raise ValueError('Output exists; use --replace to rebuild this file')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
    print(json.dumps({'requests': len(rows), 'distinct_queries': 100, 'videos': 20,
                      'human_verified': 0, 'provisional_positive': 80, 'provisional_negative': 20,
                      'validation_requests': sum(row['split'] == 'validation' for row in rows)}))


if __name__ == '__main__':
    main()
