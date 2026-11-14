"""Audit reviewed labels and explain errors without tuning on test data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from evaluate_pilot import best_iou, load_jsonl, target_result, validate_artifacts, validate_labels


def validate_review_identity(rows, reference):
    """Queries may be edited before inference; the selected video/split may not."""
    original = {row['query_id']: row for row in reference}
    if len(original) != len(reference) or set(original) != {row['query_id'] for row in rows}:
        raise ValueError('Reviewed and source annotation query IDs must match exactly')
    for row in rows:
        if any(row.get(key) != original[row['query_id']].get(key) for key in
               ('target_video_id', 'relative_source', 'duration_s', 'split')):
            raise ValueError('Reviewed annotation changed video identity or split: ' + row['query_id'])


def validation_score_analysis(rows, predictions, model):
    values = {(value['model'], value['query_id']): value for value in predictions}
    validation = [row for row in rows if row['split'] == 'validation']
    positive = [row for row in validation if row['relevant_windows']]
    negative = [row for row in validation if not row['relevant_windows']]
    correct_scores = [values[(model, row['query_id'])]['windows'][0][2] for row in positive
                      if best_iou(values[(model, row['query_id'])]['windows'][0], row['relevant_windows']) >= 0.5]
    negative_scores = [values[(model, row['query_id'])]['windows'][0][2] for row in negative]
    thresholds = []
    for threshold in (0.5, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995):
        thresholds.append({'threshold': threshold,
                           'accepted_positive_pairs': sum(values[(model, row['query_id'])]['windows'][0][2] >= threshold for row in positive),
                           'correct_localized_positive_pairs_iou_0_5': sum(score >= threshold for score in correct_scores),
                           'accepted_negative_pairs': sum(score >= threshold for score in negative_scores)})
    best_correct = max(correct_scores, default=None)
    worst_negative = max(negative_scores, default=None)
    return {'split_used': 'validation_only', 'positive_pairs': len(positive), 'negative_pairs': len(negative),
            'correct_localized_pairs_before_threshold': len(correct_scores),
            'highest_correct_localization_score': best_correct,
            'highest_negative_pair_score': worst_negative,
            'can_keep_any_correct_and_reject_all_known_validation_negatives_with_one_cutoff':
                best_correct is not None and (worst_negative is None or best_correct > worst_negative),
            'grid': thresholds,
            'decision': 'Diagnostic only; no deployment cutoff selected or tuned on test.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--reference-labels', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    rows, reference = load_jsonl(args.labels), load_jsonl(args.reference_labels)
    baseline, predictions = load_jsonl(args.baseline), load_jsonl(args.predictions)
    validate_labels(rows)
    validate_review_identity(rows, reference)
    # Compare artifacts to final reviewed query text, not the editable source suggestion.
    validate_artifacts(rows, baseline, predictions)
    old = {row['query_id']: row for row in reference}
    legacy = {row['query_id']: row for row in baseline}
    models = sorted({value['model'] for value in predictions})
    indexed = {(value['model'], value['query_id']): value for value in predictions}
    audit = []
    cases = []
    for row in rows:
        changed = [key for key in ('query', 'query_vi', 'pair_relation', 'relevant_windows')
                   if old[row['query_id']].get(key) != row.get(key)]
        if changed:
            audit.append({'query_id': row['query_id'], 'changed_fields': changed,
                          'old_relation': old[row['query_id']]['pair_relation'], 'relation': row['pair_relation'],
                          'old_query': old[row['query_id']]['query'], 'query': row['query'],
                          'old_windows': old[row['query_id']]['relevant_windows'], 'windows': row['relevant_windows']})
        body = legacy[row['query_id']]['body']
        ids = [result['video_id'] for result in body['results']]
        target = target_result(body, row['target_video_id'])
        for model in models:
            start, end, score = indexed[(model, row['query_id'])]['windows'][0]
            positive = bool(row['relevant_windows'])
            iou = best_iou([start, end], row['relevant_windows']) if positive else None
            reasons = []
            if positive and target is None:
                reasons.append('target_missing_from_legacy_top20')
            if positive and iou < 0.5:
                reasons.append('top1_localization_below_iou_0_5')
            if (end - start) / row['duration_s'] >= 0.8:
                reasons.append('top1_span_covers_at_least_80pct_of_video')
            if not positive and score >= 0.5:
                reasons.append('negative_pair_high_score_at_diagnostic_0_5')
            cases.append({'query_id': row['query_id'], 'split': row['split'], 'query': row['query'],
                          'video_id': row['target_video_id'], 'pair_relation': row['pair_relation'],
                          'truth_windows': json.dumps(row['relevant_windows']),
                          'legacy_target_rank': ids.index(row['target_video_id']) + 1 if target else None,
                          'legacy_empty': not ids, 'legacy_unconfirmed_concepts': json.dumps(body.get('unconfirmed_concepts', [])),
                          'model': model, 'top1_start_s': start, 'top1_end_s': end, 'top1_score': score,
                          'top1_iou': iou, 'failure_flags': '|'.join(reasons)})
    report = {
        'labels_sha256': hashlib.sha256(args.labels.read_bytes()).hexdigest(),
        'human_verified_pairs': len(rows), 'positive_pairs': sum(bool(row['relevant_windows']) for row in rows),
        'negative_pairs': sum(not row['relevant_windows'] for row in rows),
        'changed_record_count': len(audit),
        'changed_label_count': sum(any(key in row['changed_fields'] for key in ('pair_relation', 'relevant_windows')) for row in audit),
        'changed_query_count': sum('query' in row['changed_fields'] for row in audit), 'label_changes': audit,
        'validation_score_analysis': {model: validation_score_analysis(rows, predictions, model) for model in models},
        'failure_counts': {model: {flag: sum(flag in case['failure_flags'] for case in cases if case['model'] == model)
                                  for flag in ['target_missing_from_legacy_top20', 'top1_localization_below_iou_0_5',
                                               'top1_span_covers_at_least_80pct_of_video', 'negative_pair_high_score_at_diagnostic_0_5']}
                           for model in models},
        'interpretation': 'Flags can overlap. Known target metrics do not establish corpus-wide relevance or end-to-end improvement.',
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'reviewed-label-analysis.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    with (args.output_dir / 'reviewed-errors.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(cases)
    print(json.dumps({key: report[key] for key in ['positive_pairs', 'negative_pairs', 'changed_label_count', 'failure_counts']}))
    for model, value in report['validation_score_analysis'].items():
        print(json.dumps({'model': model, 'validation_score_analysis': value}))


if __name__ == '__main__':
    main()
