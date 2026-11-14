"""Pilot diagnostics with explicit label provenance and no false corpus recall claim."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics


def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def temporal_iou(first, second):
    if not (0 <= first[0] < first[1] and 0 <= second[0] < second[1]):
        raise ValueError('IoU requires positive, ordered intervals')
    intersection = max(0, min(first[1], second[1]) - max(first[0], second[0]))
    union = first[1] - first[0] + second[1] - second[0] - intersection
    return intersection / union


def best_iou(predicted, truth):
    return max((temporal_iou(predicted[:2], window) for window in truth), default=0.0)


def summarize_ious(values):
    if not values:
        return {'pairs': 0, 'mean_iou': None}
    return dict(pairs=len(values), mean_iou=statistics.mean(values),
                **{'r1_iou_%s' % threshold: statistics.mean(value >= threshold for value in values)
                   for threshold in (0.3, 0.5, 0.7)})


def validate_labels(rows, allow_provisional=False):
    if not rows:
        raise ValueError('An empty label set cannot produce quality scores')
    if len({row['query_id'] for row in rows}) != len(rows):
        raise ValueError('Duplicate query IDs')
    split_by_video = {}
    for row in rows:
        if not allow_provisional and not (row.get('human_verified') is True and row.get('label_status') == 'human_verified'):
            raise ValueError('Human-verified labels required. Use --allow-provisional only for explicitly provisional diagnostics.')
        if row.get('pair_relation') not in ('positive', 'negative_for_target_video'):
            raise ValueError('Unlabeled annotation requests cannot be scored as negatives')
        duration = row['duration_s']
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration <= 0:
            raise ValueError('Video duration must be positive and finite')
        if row['target_video_id'] in split_by_video and split_by_video[row['target_video_id']] != row['split']:
            raise ValueError('Video appears in both validation and test')
        split_by_video[row['target_video_id']] = row['split']
        for window in row['relevant_windows']:
            if not isinstance(window, list) or len(window) != 2 or not all(
                isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in window
            ) or not 0 <= window[0] < window[1] <= duration:
                raise ValueError('Label window lies outside video')
        if bool(row['relevant_windows']) != (row['pair_relation'] == 'positive'):
            raise ValueError('Pair relation contradicts label windows')


def target_result(body, video_id):
    return next((value for value in body.get('results', []) if value['video_id'] == video_id), None)


def validate_artifacts(rows, baseline, predictions, reference=None):
    """Reject stale/missing outputs instead of silently turning them into misses."""
    if reference is not None:
        reference_by_id = {value['query_id']: value for value in reference}
        for row in rows:
            original = reference_by_id.get(row['query_id'])
            if original is None or any(row.get(key) != original.get(key) for key in
                                       ('query', 'target_video_id', 'relative_source', 'duration_s', 'split')):
                raise ValueError('Reviewed query/video identity changed; rerun affected artifacts: ' + row['query_id'])
    baseline_by_id = {value['query_id']: value for value in baseline}
    if len(baseline_by_id) != len(baseline):
        raise ValueError('Duplicate baseline query IDs')
    models = {value['model'] for value in predictions}
    if not models:
        raise ValueError('No model predictions')
    prediction_by_key = {(value['model'], value['query_id']): value for value in predictions}
    if len(prediction_by_key) != len(predictions):
        raise ValueError('Duplicate model/query predictions')
    for row in rows:
        query_id = row['query_id']
        saved = baseline_by_id.get(query_id)
        if saved is None or saved.get('http_status') != 200:
            raise ValueError('Missing or failed baseline cannot be scored as a search miss: ' + query_id)
        if saved.get('request', {}).get('query') != row['query']:
            raise ValueError('Baseline query text changed: ' + query_id)
        for model in models:
            prediction = prediction_by_key.get((model, query_id))
            if prediction is None or prediction.get('video_id') != row['target_video_id']:
                raise ValueError('Missing prediction or mismatched target video: ' + model + '/' + query_id)
            if 'query' in prediction and prediction['query'] != row['query']:
                raise ValueError('Prediction query text changed: ' + model + '/' + query_id)
            windows = prediction.get('windows')
            if not windows:
                raise ValueError('Pilot score diagnostics require nonempty ranked model proposals')
            for window in windows:
                if len(window) != 3 or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in window):
                    raise ValueError('Model window/score must contain finite numbers')
                if not 0 <= window[0] < window[1] <= row['duration_s'] + 1e-5:
                    raise ValueError('Invalid model prediction')


def evaluate(rows, baseline, predictions):
    baseline_by_id = {value['query_id']: value for value in baseline}
    predictions_by_key = {(value['model'], value['query_id']): value for value in predictions}
    positive = [row for row in rows if row['relevant_windows']]
    negative = [row for row in rows if not row['relevant_windows']]
    report = {
        'positive_pairs': len(positive), 'negative_pairs': len(negative),
        'annotated_positive_windows': sum(len(row['relevant_windows']) for row in positive),
        'legacy_http_200': sum(baseline_by_id.get(row['query_id'], {}).get('http_status') == 200 for row in rows),
        'legacy_designated_target_hit': {}, 'grounding_given_target_video': {},
        'negative_pair_diagnostics': {}, 'per_query': [],
    }
    for k in (5, 10, 20):
        report['legacy_designated_target_hit'][str(k)] = statistics.mean(
            any(value['video_id'] == row['target_video_id'] for value in baseline_by_id.get(row['query_id'], {}).get('body', {}).get('results', [])[:k])
            for row in positive) if positive else None
    legacy_ious = []
    retrieved_ious = []
    for row in positive:
        result = target_result(baseline_by_id.get(row['query_id'], {}).get('body', {}), row['target_video_id'])
        value = best_iou([result['ts_start_s'], result['ts_end_s']], row['relevant_windows']) if result else 0
        legacy_ious.append(value)
        if result:
            retrieved_ious.append(value)
    report['legacy_designated_target_primary_window'] = summarize_ious(legacy_ious)
    report['legacy_primary_window_when_target_retrieved'] = summarize_ious(retrieved_ious)

    for model in sorted({value['model'] for value in predictions}):
        values = []
        shared_subset = []
        for row in positive:
            prediction = predictions_by_key.get((model, row['query_id']))
            if prediction is None:
                raise ValueError('Missing grounded pair: ' + model + '/' + row['query_id'])
            for start, end, score in prediction['windows']:
                if not (0 <= start < end <= row['duration_s'] + 1e-5 and math.isfinite(score)):
                    raise ValueError('Invalid model prediction')
            value = best_iou(prediction['windows'][0], row['relevant_windows']) if prediction['windows'] else 0
            values.append(value)
            if target_result(baseline_by_id.get(row['query_id'], {}).get('body', {}), row['target_video_id']):
                shared_subset.append(value)
            report['per_query'].append({'query_id': row['query_id'], 'model': model, 'top1_iou': value})
        report['grounding_given_target_video'][model] = summarize_ious(values)
        report['grounding_given_target_video'][model]['when_legacy_target_retrieved'] = summarize_ious(shared_subset)
        scores = [predictions_by_key[(model, row['query_id'])]['windows'][0][2] for row in negative]
        report['negative_pair_diagnostics'][model] = {
            'pairs': len(scores), 'top1_scores': scores,
            'top1_score_above_0_5': sum(score > 0.5 for score in scores),
            'note': '0.5 is a diagnostic threshold, not calibrated rejection or a measured corpus false positive rate.',
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-provisional', action='store_true')
    parser.add_argument('--reference-labels', type=Path, default=Path(__file__).with_name('pilot.provisional.jsonl'))
    args = parser.parse_args()
    rows = load_jsonl(args.labels)
    validate_labels(rows, args.allow_provisional)
    baseline, predictions = load_jsonl(args.baseline), load_jsonl(args.predictions)
    validate_artifacts(rows, baseline, predictions, load_jsonl(args.reference_labels))
    human_verified = all(row.get('human_verified') is True and row.get('label_status') == 'human_verified' for row in rows)
    report = {
        'label_status': 'human_verified' if human_verified else 'provisional_not_gold',
        'human_verified_pairs': sum(bool(row.get('human_verified')) for row in rows),
        'video_count': len({row['target_video_id'] for row in rows}),
        'evaluated_at_utc': datetime.now(timezone.utc).isoformat(),
        'input_fingerprints': {name: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                               for name, path in [('labels', args.labels), ('reference_labels', args.reference_labels),
                                                  ('baseline', args.baseline), ('predictions', args.predictions)]},
        'limitations': [
            'Labels cover selected query-video pairs, not all relevant videos in the corpus.',
            'Designated-target hit is not exhaustive corpus recall or precision.',
            'Grounding is given the target video; this is not the end-to-end new search flow.',
            'No checkpoint or threshold was tuned on test labels.',
            f"This evaluation covers {len({row['target_video_id'] for row in rows})} selected videos; video splits do not establish trip/camera independence.",
            'R@1 counts a query hit against any annotated window, not recovery of every disjoint window.',
        ],
        'splits': {},
    }
    if not human_verified:
        report['limitations'].append('Provisional labels were assigned from sampled frames; boundaries need human full-video review.')
    for split in ('validation', 'test'):
        selected = [row for row in rows if row['split'] == split]
        report['splits'][split] = evaluate(selected, baseline, predictions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ['label_status', 'human_verified_pairs']}))
    for split, value in report['splits'].items():
        print(json.dumps({'split': split, 'designated_target_hit': value['legacy_designated_target_hit'],
                          'oracle_grounding': value['grounding_given_target_video']}))


if __name__ == '__main__':
    main()
