"""Assemble and audit completed Group B runs; never changes reviewed input labels."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys

from analyze_reviewed_pilot import validate_review_identity
from evaluate_pilot import best_iou, load_jsonl, summarize_ious, target_result, validate_artifacts, validate_labels

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def fingerprint(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write_jsonl(path, rows):
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def timing(values):
    return {'observations': len(values), 'min_ms': min(values), 'median_ms': statistics.median(values),
            'max_ms': max(values), 'total_ms': sum(values)}


def dataset_counts(rows):
    return {'pairs': len(rows), 'positive_pairs': sum(bool(row['relevant_windows']) for row in rows),
            'negative_pairs': sum(not row['relevant_windows'] for row in rows),
            'videos': len({row['target_video_id'] for row in rows}),
            'positive_windows': sum(len(row['relevant_windows']) for row in rows),
            'multiple_window_pairs': sum(len(row['relevant_windows']) > 1 for row in rows)}


def stage_diagnostics(rows, baseline, predictions):
    saved = {row['query_id']: row for row in baseline}
    models = sorted({row['model'] for row in predictions})
    indexed = {(row['model'], row['query_id']): row for row in predictions}
    result = {}
    for split in ('validation', 'test'):
        positive = [row for row in rows if row['split'] == split and row['relevant_windows']]
        missing = [row for row in positive if not target_result(saved[row['query_id']]['body'], row['target_video_id'])]
        empty = [row for row in positive if not saved[row['query_id']]['body'].get('results')]
        buckets = {}
        for name, lower, upper in [('up_to_10s', 0, 10), ('10_to_20s', 10, 20), ('over_20s', 20, float('inf'))]:
            selected = [row for row in positive if lower < max(end - start for start, end in row['relevant_windows']) <= upper]
            buckets[name] = {'pairs': len(selected), 'grounding_given_target_video': {
                model: summarize_ious([best_iou(indexed[(model, row['query_id'])]['windows'][0], row['relevant_windows'])
                                       for row in selected]) for model in models}}
        result[split] = {
            'positive_pairs': len(positive), 'target_missing_top20': len(missing),
            'empty_search_on_positive_pair': len(empty),
            'empty_with_unconfirmed_concepts': sum(bool(saved[row['query_id']]['body'].get('unconfirmed_concepts')) for row in empty),
            'missing_target_query_ids': [row['query_id'] for row in missing],
            'longest_annotated_window_buckets': buckets,
            'note': 'Only the designated video is labeled. An absent target does not prove other returned videos irrelevant.',
        }
    return result


def write_checkpoint_review(root, out, combined):
    media = {}
    for name in ('annotation-review.html', 'expansion-review.html'):
        source = (root / name).read_text(encoding='utf-8')
        embedded = re.search(r'<script id="data" type="application/json">(.*?)</script>', source, re.S)
        if embedded is None:
            raise ValueError('Missing source playback locators in ' + name)
        media.update({row['video_id']: row['preview_url'] for row in json.loads(embedded.group(1))['videos']})
    baseline = {row['query_id']: row['body'] for row in combined['baseline']}
    predictions = {(row['model'], row['query_id']): row for row in combined['predictions']}
    rows = []
    for row in combined['labels']:
        body = baseline[row['query_id']]
        target = target_result(body, row['target_video_id'])
        positive = bool(row['relevant_windows'])
        legacy_window = [target['ts_start_s'], target['ts_end_s']] if target else None
        rows.append({
            'query_id': row['query_id'], 'query': row['query'], 'query_vi': row.get('query_vi', row['query']),
            'split': row['split'], 'video_id': row['target_video_id'], 'duration_s': row['duration_s'],
            'relation': row['pair_relation'], 'truth': row['relevant_windows'],
            'media_url': media[row['target_video_id']], 'legacy_window': legacy_window,
            'legacy_iou': best_iou(legacy_window, row['relevant_windows']) if positive and target else None,
            'legacy_rank': next((index + 1 for index, result in enumerate(body['results']) if result['video_id'] == row['target_video_id']), None),
            'models': [{'model': model, 'window': predictions[(model, row['query_id'])]['windows'][0],
                        'iou': best_iou(predictions[(model, row['query_id'])]['windows'][0], row['relevant_windows']) if positive else None}
                       for model in ('qd_detr', 'cg_detr')],
        })
    payload = json.dumps({'rows': rows}, ensure_ascii=False).replace('<', '\\u003c')
    template = (HERE / 'checkpoint-review-template.html').read_text(encoding='utf-8')
    (out / 'checkpoint-review.html').write_text(template.replace('__DATA__', payload), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=REPO / 'data/temporal-search/group-b')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    root = args.data_root.resolve()
    out = (args.output_dir or root / 'reviewed-evaluation').resolve()
    if out == root or root not in out.parents:
        raise ValueError('Generated evaluation must be in a separate subdirectory of the data root')
    cohorts = {
        'pilot': (root / 'pilot.reviewed.jsonl', HERE / 'pilot.provisional.jsonl',
                  root / 'legacy-baseline.jsonl', root / 'grounding-cpu/predictions.jsonl', root / 'grounding-cpu/summary.json', 20),
        'expansion': (root / 'expansion.reviewed.jsonl', root / 'expansion.requests.jsonl',
                      root / 'expansion-baseline.jsonl', root / 'expansion-grounding-cpu/predictions.jsonl',
                      root / 'expansion-grounding-cpu/summary.json', 100),
    }
    combined = {'labels': [], 'reference': [], 'baseline': [], 'predictions': []}
    inputs, statistics_by_cohort, timings = {}, {}, {}
    for name, (labels_path, reference_path, baseline_path, predictions_path, summary_path, expected_count) in cohorts.items():
        labels, reference = load_jsonl(labels_path), load_jsonl(reference_path)
        baseline, predictions = load_jsonl(baseline_path), load_jsonl(predictions_path)
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        if len(labels) != expected_count or len(baseline) != expected_count or len(predictions) != 2 * expected_count:
            raise ValueError('Incomplete run for ' + name)
        if {row['model'] for row in predictions} != {'qd_detr', 'cg_detr'}:
            raise ValueError('Both checkpoint outputs are required for ' + name)
        if {row['query_id'] for row in baseline} != {row['query_id'] for row in labels}:
            raise ValueError('Baseline query identities differ for ' + name)
        if name == 'expansion':
            label_hash = fingerprint(labels_path)['sha256']
            if summary.get('input_labels_sha256') != label_hash or any(row.get('input_labels_sha256') != label_hash for row in predictions):
                raise ValueError('Expansion inference was not run on these exact reviewed labels')
        if summary['device'] != 'cpu' or not all(row['strict_load'] for row in summary['model_info']):
            raise ValueError('Unexpected checkpoint runtime provenance')
        validate_labels(labels)
        validate_review_identity(labels, reference)
        validate_artifacts(labels, baseline, predictions)
        for key, values in [('labels', labels), ('reference', reference), ('baseline', baseline), ('predictions', predictions)]:
            combined[key].extend(values)
        for key, path in [('labels', labels_path), ('reference', reference_path), ('baseline', baseline_path),
                          ('predictions', predictions_path), ('summary', summary_path)]:
            inputs[name + '_' + key] = fingerprint(path)
        original = {row['query_id']: row for row in reference}
        statistics_by_cohort[name] = {
            **dataset_counts(labels), 'query_edits': sum(row['query'] != original[row['query_id']]['query'] for row in labels),
            'label_edits': sum(any(row[key] != original[row['query_id']][key] for key in ('pair_relation', 'relevant_windows')) for row in labels),
            'splits': {split: dataset_counts([row for row in labels if row['split'] == split]) for split in ('validation', 'test')},
        }
        timings[name] = {
            'process_elapsed_s': summary['process_elapsed_s'], 'clip_load_ms': summary['clip_load_ms'],
            'head_load_ms': {row['model']: row['load_ms'] for row in summary['model_info']},
            'decode': timing([row['decode_ms'] for row in summary['video_timings']]),
            'image_encode': timing([row['image_encode_ms'] for row in summary['video_timings']]),
            'text_encode': timing([row['text_encode_ms'] for row in summary['text_timings']]),
            'head': {model: timing([row['grounding_ms'] for row in predictions if row['model'] == model]) for model in ('qd_detr', 'cg_detr')},
            'peak_process_rss_mib': summary['peak_process_rss_mib'],
            'legacy_http': timing([row['client_elapsed_ms'] for row in baseline]),
            'limitations': 'Observed different-query times, not controlled cold/warm latency. CPU experiment and legacy collection overlapped. Head timing excludes encoding/retrieval/HTTP.',
        }
    validate_labels(combined['labels'])
    validate_artifacts(combined['labels'], combined['baseline'], combined['predictions'])
    manifest_path = out / 'input-manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding='utf-8'))['inputs'] != inputs:
        raise ValueError('Previous evaluation inputs differ; inspect them before choosing a different output directory')
    out.mkdir(parents=True, exist_ok=True)
    paths = {key: out / (key + '.jsonl') for key in combined}
    for key, rows in combined.items():
        write_jsonl(paths[key], rows)
    manifest = {
        'inputs': inputs, 'cohorts': statistics_by_cohort,
        'combined': {**dataset_counts(combined['labels']),
                     'distinct_query_texts': len({row['query'].casefold() for row in combined['labels']}),
                     'splits': {split: dataset_counts([row for row in combined['labels'] if row['split'] == split]) for split in ('validation', 'test')}},
        'timings': timings,
        'limitations': ['Single human reviewer; no inter-rater agreement measured.',
                        'Selected dashcam videos and related queries are not independent random samples.',
                        'Many negative controls are simple day/night/snow contrasts, not a hard-negative benchmark.',
                        'Pilot model outputs predate human review; query/video identities were unchanged.',
                        'Expansion outputs use final human-edited queries; no tuning on test.',
                        'All grounding measurements are given the correct target video, not end-to-end temporal search.'],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    for name, labels_path, baseline_path, predictions_path in [
            ('expansion', cohorts['expansion'][0], cohorts['expansion'][2], cohorts['expansion'][3]),
            ('combined', paths['labels'], paths['baseline'], paths['predictions'])]:
        subprocess.run([sys.executable, str(HERE / 'evaluate_pilot.py'), '--labels', str(labels_path),
                        '--reference-labels', str(labels_path), '--baseline', str(baseline_path),
                        '--predictions', str(predictions_path), '--output', str(out / (name + '-diagnostics.json'))], check=True)
    subprocess.run([sys.executable, str(HERE / 'analyze_reviewed_pilot.py'),
                    '--labels', str(paths['labels']), '--reference-labels', str(paths['reference']),
                    '--baseline', str(paths['baseline']), '--predictions', str(paths['predictions']),
                    '--output-dir', str(out)], check=True)
    (out / 'stage-diagnostics.json').write_text(json.dumps(stage_diagnostics(combined['labels'], combined['baseline'], combined['predictions']), indent=2) + '\n', encoding='utf-8')
    write_checkpoint_review(root, out, combined)
    print(json.dumps({'output': str(out), 'combined': manifest['combined']}))


if __name__ == '__main__':
    main()
