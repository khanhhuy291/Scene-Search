"""Validate design examples without importing the legacy backend or loading models."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def request_semantics(value):
    require(bool(value['query'].strip()), 'Query cannot be whitespace')
    k = value.get('candidate_video_count', 10)
    require(value.get('limit', 10) <= k, 'limit cannot exceed candidate_video_count')
    if value.get('grounding_query') is not None:
        require(bool(value['grounding_query'].strip()), 'grounding_query cannot be whitespace')
    if value.get('query_language') == 'vi':
        require(bool(value.get('grounding_query')), 'Design examples need a verified grounding query for Vietnamese')
    window = value.get('filters', {}).get('time_range_s')
    if window is not None:
        require(window[0] < window[1], 'Filter window must have positive duration')


def response_semantics(value, request=None):
    counts = value['counts']
    received = counts['candidate_videos_received']
    processed = counts['candidate_videos_processed']
    skipped = counts['candidate_videos_skipped']
    results = value['results']
    require(processed + skipped == received, 'Processed and skipped counts must account for every candidate')
    require(counts['returned_videos'] == len(results), 'Returned count must match results')
    require(len(results) <= processed, 'Cannot return an unprocessed video')
    require(len({item['video_id'] for item in results}) == len(results), 'Duplicate video IDs')
    retrieval = value['retrieval']
    if retrieval['provider'] == 'legacy-api':
        require(retrieval['raw_ann_count'] is None, 'Legacy API does not expose raw ANN count')
        require(retrieval['scene_count_scope'] == 'returned_matched_moments', 'Legacy scene scope must be honest')
    else:
        require(retrieval['scene_count_scope'] == 'raw_ann', 'Qdrant provider must identify the raw scene pool')
        require(isinstance(retrieval['raw_ann_count'], int), 'Raw provider requires an ANN count')
        require(retrieval['raw_ann_count'] >= counts['candidate_scenes_observed'], 'Observed scenes cannot exceed raw pool')
    incomplete = skipped > 0 or retrieval['upstream_degraded'] or retrieval['truncated']
    if value['status'] in ('complete', 'no_match'):
        require(not incomplete, 'Degraded/truncated/skipped work cannot be complete or no_match')
    if value['status'] == 'complete':
        require(bool(results), 'Empty completed response must use no_match')
    if value['status'] == 'no_match':
        require(not results, 'no_match cannot contain results')
    if value['status'] == 'partial':
        require(bool(value['warnings']), 'Partial response must explain the missing work')
        require(incomplete, 'Partial response needs incomplete work')
        require(processed > 0 or retrieval['truncated'] or retrieval['upstream_degraded'], 'All failed candidates require an error response')
    seen_moments = set()
    seen_scenes = set()
    for result in results:
        duration = result['video_duration_s']
        playback = result['playback']
        for scene in result['evidence_scenes']:
            require(0 <= scene['ts_start_s'] < scene['ts_end_s'] <= duration, 'Evidence window outside video')
            require(scene['scene_id'] not in seen_scenes, 'Duplicate scene evidence')
            seen_scenes.add(scene['scene_id'])
        if playback['kind'] == 'unavailable':
            require(playback['url'] is None and playback['origin_s'] == playback['duration_s'] == 0,
                    'Unavailable playback must not invent media')
        else:
            require(bool(playback['url']), 'Available playback needs a URL')
            require(playback['duration_s'] > 0, 'Available playback needs positive duration')
            require(playback['origin_s'] + playback['duration_s'] <= duration, 'Playback lies outside source timeline')
            if playback['kind'] == 'full_video':
                require(playback['origin_s'] == 0, 'Full video must start at source origin')
        for moment in result['moments']:
            start, end = moment['ts_start_s'], moment['ts_end_s']
            require(0 <= start < end <= duration, 'Predicted window outside video')
            require(math.isfinite(moment['grounding_score']), 'Model score must be finite')
            require(moment['moment_id'] not in seen_moments, 'Duplicate moment ID')
            seen_moments.add(moment['moment_id'])
            if playback['url']:
                require(playback['origin_s'] <= start < end <= playback['origin_s'] + playback['duration_s'],
                        'Playback cannot cover this moment with the given origin')
            if request:
                require(len(result['moments']) <= request.get('moments_per_video', 3), 'Too many moments')
                window = request.get('filters', {}).get('time_range_s')
                if window:
                    require(window[0] <= start < end <= window[1], 'Moment violates the requested time range')
    require(len(seen_scenes) <= counts['candidate_scenes_observed'], 'Evidence exceeds observed scene count')
    if request:
        require(received <= request.get('candidate_video_count', 10), 'Too many candidate videos')
        require(len(results) <= request.get('limit', 10), 'Too many returned videos')


def main():
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import ValidationError
    except ImportError as error:
        raise SystemExit('Use a Python environment with jsonschema. Do not add it to legacy app dependencies.') from error
    contract = json.loads((ROOT / 'contracts/openapi.json').read_text(encoding='utf-8'))
    examples = json.loads((ROOT / 'contracts/examples.json').read_text(encoding='utf-8'))
    require(contract['openapi'] == '3.1.0', 'Expected the declared OpenAPI dialect')
    require('/api/v1/search' not in contract['paths'], 'Do not redefine the legacy route')
    schemas = contract['components']['schemas']
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)

    def check_refs(node):
        if isinstance(node, dict):
            if '$ref' in node:
                require(node['$ref'].startswith('#/'), 'Only local design references are allowed')
                target = contract
                for part in node['$ref'][2:].split('/'):
                    target = target[part.replace('~1', '/').replace('~0', '~')]
            for child in node.values():
                check_refs(child)
        elif isinstance(node, list):
            for child in node:
                check_refs(child)
    check_refs(contract)

    def finite_numbers(node):
        if isinstance(node, float):
            require(math.isfinite(node), 'JSON numbers must be finite')
        elif isinstance(node, dict):
            for child in node.values():
                finite_numbers(child)
        elif isinstance(node, list):
            for child in node:
                finite_numbers(child)

    def validate(name, value):
        finite_numbers(value)
        validator = Draft202012Validator({'$ref': '#/components/schemas/' + name, 'components': contract['components']})
        validator.validate(value)
        if name == 'TemporalSearchRequest':
            request_semantics(value)
        elif name == 'TemporalSearchResponse':
            response_semantics(value, examples['requests']['english'])

    for value in examples['requests'].values():
        validate('TemporalSearchRequest', value)
    for value in examples['responses'].values():
        validate('TemporalSearchResponse', value)
    for value in examples['errors'].values():
        validate('ErrorResponse', value)

    operation = contract['paths']['/api/v1/temporal-search']['post']
    require({key: item['value'] for key, item in operation['requestBody']['content']['application/json']['examples'].items()} == examples['requests'],
            'Embedded request examples drifted')
    require({key: item['value'] for key, item in operation['responses']['200']['content']['application/json']['examples'].items()} == examples['responses'],
            'Embedded response examples drifted')

    bad = []
    value = copy.deepcopy(examples['requests']['english']); value['query'] = '   '
    bad.append(('blank_query', 'TemporalSearchRequest', value))
    value = copy.deepcopy(examples['requests']['english']); value['limit'] = 11
    bad.append(('limit_exceeds_candidates', 'TemporalSearchRequest', value))
    value = copy.deepcopy(examples['requests']['english']); value['mode'] = 'temporal'
    bad.append(('legacy_mode_in_new_request', 'TemporalSearchRequest', value))
    value = copy.deepcopy(examples['requests']['english']); value['filters'] = {'time_range_s': [20, 10]}
    bad.append(('reversed_filter', 'TemporalSearchRequest', value))
    value = copy.deepcopy(examples['responses']['complete']); value['results'][0]['moments'][0]['ts_end_s'] = 41
    bad.append(('moment_outside_video', 'TemporalSearchResponse', value))
    value = copy.deepcopy(examples['responses']['complete']); value['counts']['returned_videos'] = 2
    bad.append(('wrong_counts', 'TemporalSearchResponse', value))
    value = copy.deepcopy(examples['responses']['complete']); value['retrieval']['raw_ann_count'] = 8
    bad.append(('invented_raw_ann_count', 'TemporalSearchResponse', value))
    value = copy.deepcopy(examples['responses']['partial']); value['status'] = 'complete'
    bad.append(('hidden_partial_failure', 'TemporalSearchResponse', value))
    value = copy.deepcopy(examples['responses']['complete']); value['results'][0]['playback'] = {
        'url': 'http://127.0.0.1:8000/api/v1/media/clip/example', 'kind': 'subclip',
        'origin_s': 20, 'duration_s': 10, 'privacy_state': 'source_preserving'}
    bad.append(('wrong_playback_origin', 'TemporalSearchResponse', value))
    for label, name, value in bad:
        try:
            validate(name, value)
        except (ValueError, ValidationError):
            pass
        else:
            raise AssertionError('Invalid example accepted: ' + label)
    print(json.dumps({'schemas_checked': len(schemas), 'valid_requests': len(examples['requests']),
                      'valid_responses': len(examples['responses']), 'valid_errors': len(examples['errors']),
                      'invalid_examples_rejected': len(bad), 'legacy_backend_imported': False,
                      'server_tested': False}, indent=2))


if __name__ == '__main__':
    main()
