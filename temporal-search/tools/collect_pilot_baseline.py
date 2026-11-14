"""Collect legacy search responses for the pilot without changing search defaults."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from legacy_baseline import sanitized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queries', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--api-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    if args.api_url not in ('http://127.0.0.1:8000', 'http://localhost:8000'):
        raise ValueError('Pilot collector is limited to the existing local API')
    rows = [json.loads(line) for line in args.queries.read_text(encoding='utf-8').splitlines() if line.strip()]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if args.output.exists():
        existing = {row['query_id']: row for row in map(json.loads, args.output.read_text(encoding='utf-8').splitlines())}
    with args.output.open('a', encoding='utf-8') as stream:
        for row in rows:
            if row['query_id'] in existing:
                if existing[row['query_id']].get('request', {}).get('query') != row['query']:
                    raise ValueError('Existing baseline query changed; use a new output filename: ' + row['query_id'])
                continue
            payload = {'query': row['query'], 'limit': 20}
            request = Request(args.api_url + '/api/v1/search', data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
            started = time.perf_counter()
            try:
                with urlopen(request, timeout=90) as response:
                    record = {'http_status': response.status, 'body': sanitized(json.load(response))}
            except HTTPError as error:
                record = {'http_status': error.code, 'error_type': 'HTTPError'}
            except (URLError, TimeoutError, OSError) as error:
                record = {'http_status': None, 'error_type': type(error).__name__}
            record.update(query_id=row['query_id'], request=payload,
                          captured_at_utc=datetime.now(timezone.utc).isoformat(),
                          client_elapsed_ms=round((time.perf_counter() - started) * 1000, 2))
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            stream.flush()
            print(json.dumps({'query_id': row['query_id'], 'http_status': record['http_status'],
                              'results': len(record.get('body', {}).get('results', [])),
                              'elapsed_ms': record['client_elapsed_ms']}), flush=True)


if __name__ == '__main__':
    main()
