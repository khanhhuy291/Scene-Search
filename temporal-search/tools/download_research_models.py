"""Download the bounded research weight set to an explicit experiment directory."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

CLIP_SHA = '40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af'
FILES = [
    ('ViT-B-32.pt', 'https://openaipublic.azureedge.net/clip/models/' + CLIP_SHA + '/ViT-B-32.pt', 'sha256', CLIP_SHA),
    ('author_qd_detr_clip.ckpt', 'https://raw.githubusercontent.com/wjun0830/QD-DETR/f8628f79f7c651b586300b142dbe9b85e43857cc/run_on_video/qd_detr_ckpt/model_best.ckpt', 'git-blob', None),
    ('author_cg_detr_clip.ckpt', 'https://media.githubusercontent.com/media/wjun0830/CGDETR/212b2e49a0893512930d63b9294a8c066347e606/run_on_video/CLIP_ckpt/qvhighlights_onlyCLIP/model_best.ckpt', 'sha256', 'd51eef06e8908a84f8000f1c2b70a9d7f4b6bdd570d4b5b6a97bcdbf90e66f2c'),
]


def digest(path, algorithm):
    if algorithm == 'git-blob':
        result = hashlib.sha1()
        result.update(('blob %d\0' % path.stat().st_size).encode('ascii'))
        algorithm = None
    else:
        result = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def download(root, item):
    name, url, algorithm, expected = item
    if algorithm == 'git-blob':
        metadata_url = 'https://api.github.com/repos/wjun0830/QD-DETR/contents/run_on_video/qd_detr_ckpt/model_best.ckpt?ref=f8628f79f7c651b586300b142dbe9b85e43857cc'
        with urlopen(Request(metadata_url, headers={'User-Agent': 'SceneSearch-research/1.0'}), timeout=30) as response:
            expected = json.load(response)['sha']
    destination = root / name
    if not destination.exists() or digest(destination, algorithm) != expected:
        temporary = destination.with_suffix(destination.suffix + '.part')
        request = Request(url, headers={'User-Agent': 'SceneSearch-research/1.0'})
        with urlopen(request, timeout=90) as response, temporary.open('wb') as stream:
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 500 * 1024 * 1024:
                    raise ValueError('Unexpectedly large weight file: ' + name)
                stream.write(chunk)
        if digest(temporary, algorithm) != expected:
            raise ValueError('Published checksum mismatch: ' + name)
        temporary.replace(destination)
    record = {'name': name, 'url': url, 'published_checksum': algorithm + ':' + expected,
              'sha256': digest(destination, 'sha256'), 'bytes': destination.stat().st_size}
    print(json.dumps(record), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, required=True)
    args = parser.parse_args()
    root = args.model_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(lambda item: download(root, item), FILES))
    (root / 'weights-manifest.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
