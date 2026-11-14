"""Worked examples for interval metrics and safeguards against invalid evaluation."""
import unittest

from evaluate_pilot import best_iou, temporal_iou, target_result, validate_artifacts, validate_labels
from analyze_reviewed_pilot import validate_review_identity


class PilotMetricsTests(unittest.TestCase):
    def test_partial_overlap_is_one_third(self):
        self.assertAlmostEqual(temporal_iou([0, 10], [5, 15]), 1 / 3)

    def test_touching_half_open_intervals_do_not_overlap(self):
        self.assertEqual(temporal_iou([0, 5], [5, 10]), 0)

    def test_zero_length_is_not_a_perfect_match(self):
        with self.assertRaises(ValueError):
            temporal_iou([5, 5], [5, 5])

    def test_other_relevant_looking_video_does_not_count_as_target(self):
        self.assertIsNone(target_result({'results': [{'video_id': 'other'}]}, 'target'))

    def test_unverified_labels_cannot_produce_official_scores(self):
        with self.assertRaises(ValueError):
            validate_labels([{'query_id': 'one', 'human_verified': False}])

    def test_video_split_leakage_is_rejected(self):
        shared = {'target_video_id': 'v', 'duration_s': 40, 'pair_relation': 'positive', 'relevant_windows': [[1, 2]]}
        with self.assertRaises(ValueError):
            validate_labels([dict(shared, query_id='one', split='validation'), dict(shared, query_id='two', split='test')], True)

    def test_second_disjoint_truth_window_is_a_valid_match(self):
        self.assertEqual(best_iou([27, 35], [[3, 5], [27, 35]]), 1)

    def test_empty_labels_do_not_get_human_verified_scores(self):
        with self.assertRaisesRegex(ValueError, 'empty label set'):
            validate_labels([])

    def test_unlabeled_expansion_tasks_are_not_negative_pairs(self):
        with self.assertRaisesRegex(ValueError, 'Unlabeled'):
            validate_labels([{'query_id': 'one', 'pair_relation': 'unlabeled'}], True)

    def test_wrong_video_prediction_is_rejected(self):
        label = {'query_id': 'one', 'query': 'A car', 'target_video_id': 'correct'}
        baseline = [{'query_id': 'one', 'http_status': 200, 'request': {'query': 'A car'}}]
        predictions = [{'query_id': 'one', 'video_id': 'wrong', 'model': 'model'}]
        with self.assertRaisesRegex(ValueError, 'mismatched target video'):
            validate_artifacts([label], baseline, predictions)

    def test_http_failure_is_not_a_retrieval_miss(self):
        label = {'query_id': 'one', 'query': 'A car', 'target_video_id': 'correct'}
        with self.assertRaisesRegex(ValueError, 'failed baseline'):
            validate_artifacts([label], [{'query_id': 'one', 'http_status': 503}], [{'model': 'model', 'query_id': 'one'}])

    def test_changed_query_requires_new_outputs(self):
        label = {'query_id': 'one', 'query': 'A bus', 'target_video_id': 'correct'}
        reference = [{'query_id': 'one', 'query': 'A car', 'target_video_id': 'correct'}]
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            validate_artifacts([label], [], [], reference)

    def test_editing_query_before_inference_preserves_review_selection(self):
        original = {'query_id': 'one', 'query': 'Turns right', 'target_video_id': 'v',
                    'relative_source': 'v.mov', 'duration_s': 40, 'split': 'test'}
        reviewed = dict(original, query='Turns left')
        validate_review_identity([reviewed], [original])

    def test_review_cannot_move_query_to_another_video(self):
        original = {'query_id': 'one', 'target_video_id': 'v', 'split': 'test'}
        with self.assertRaisesRegex(ValueError, 'video identity or split'):
            validate_review_identity([dict(original, target_video_id='other')], [original])

    def test_edited_query_cannot_reuse_stale_baseline(self):
        reviewed = {'query_id': 'one', 'query': 'Turns left', 'target_video_id': 'v'}
        baseline = [{'query_id': 'one', 'http_status': 200, 'request': {'query': 'Turns right'}}]
        predictions = [{'query_id': 'one', 'model': 'model', 'video_id': 'v'}]
        with self.assertRaisesRegex(ValueError, 'Baseline query text changed'):
            validate_artifacts([reviewed], baseline, predictions)


if __name__ == '__main__':
    unittest.main()
