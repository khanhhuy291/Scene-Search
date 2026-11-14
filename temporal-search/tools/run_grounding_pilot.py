"""Bounded raw-video checkpoint experiment; no API, training or production indexing.

Uses the pinned upstream Lighthouse heads and shared OpenAI CLIP weights.
The author's inference preprocessing is reproduced with normalized clip/token
features. Display rotation is respected before resize/crop. Checkpoint paths
must refer to the verified official files downloaded by the companion tool.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import time

STARTED = time.perf_counter()

import av
import clip
from easydict import EasyDict
import imageio_ffmpeg
import numpy as np
import torch
from torch.nn import functional as F


def timed(device, function):
    if device == 'cuda':
        torch.cuda.synchronize()
    started = time.perf_counter()
    result = function()
    if device == 'cuda':
        torch.cuda.synchronize()
    return result, round((time.perf_counter() - started) * 1000, 3)


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def decode(path):
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        first = next(container.decode(stream))
        rotation = getattr(first, 'rotation', 0) or 0
        if not rotation and stream.metadata.get('rotate'):
            rotation = -float(stream.metadata['rotate'])
        width, height = stream.width, stream.height
        if round(rotation / 90) % 2:
            width, height = height, width
        duration = float(stream.duration * stream.time_base) if stream.duration else container.duration / av.time_base
    if not 0 < duration <= 150:
        raise ValueError('Pilot only supports videos up to 150 seconds')
    if height >= width:
        scaled_height, scaled_width = int(height * 224 / width), 224
    else:
        scaled_height, scaled_width = 224, int(width * 224 / height)
    filters = 'fps=0.5,scale=%d:%d,crop=224:224:%d:%d' % (
        scaled_width, scaled_height, (scaled_width - 224) // 2, (scaled_height - 224) // 2)
    # FFmpeg autorotation applies display matrix before these filters.
    command = [imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-threads', '2', '-i', str(path),
               '-an', '-vf', filters, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-threads', '2', 'pipe:1']
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode('utf-8', errors='replace')[-1000:])
    frames = np.frombuffer(completed.stdout, dtype=np.uint8).reshape(-1, 224, 224, 3).copy()
    if not 1 <= len(frames) <= 75:
        raise ValueError('Unexpected clip count')
    return frames, {'duration_s': duration, 'display_rotation_ccw': rotation,
                    'display_width': width, 'display_height': height,
                    'clip_count': len(frames), 'model_duration_s': len(frames) * 2.0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queries', type=Path, required=True)
    parser.add_argument('--raw-root', type=Path, required=True)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cuda')
    parser.add_argument('--image-batch-size', type=int, default=4)
    args = parser.parse_args()
    torch.set_num_threads(2)
    torch.manual_seed(42)
    if args.device == 'cuda':
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA requested but unavailable')
        free, _ = torch.cuda.mem_get_info()
        if free < 768 * 1024 * 1024:
            raise RuntimeError('Insufficient free VRAM for the bounded pilot')
        torch.cuda.reset_peak_memory_stats()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in args.queries.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    labels_sha256 = fingerprint(args.queries)
    expected = {record['name']: record for record in json.loads((args.models / 'weights-manifest.json').read_text())}
    for name in ('ViT-B-32.pt', 'author_qd_detr_clip.ckpt', 'author_cg_detr_clip.ckpt'):
        if fingerprint(args.models / name) != expected[name]['sha256']:
            raise ValueError('Verified weight changed: ' + name)
    encoder, load_ms = timed(args.device, lambda: clip.load(str(args.models / 'ViT-B-32.pt'), device=args.device, jit=True)[0])
    encoder.eval()
    print(json.dumps({'phase': 'clip_loaded', 'ms': load_ms}), flush=True)
    mean = torch.tensor([0.48145466, 0.4578275, 0.40821073], device=args.device).view(1, 3, 1, 1)
    std = torch.tensor([0.26862954, 0.26130258, 0.27577711], device=args.device).view(1, 3, 1, 1)
    video_features = {}
    feature_timings = []
    with torch.inference_mode():
        for row in rows:
            video_id = row['target_video_id']
            if video_id in video_features:
                continue
            source = (args.raw_root / row['relative_source']).resolve()
            if args.raw_root.resolve() not in source.parents:
                raise ValueError('Source escaped raw root')
            (frames, metadata), decode_ms = timed(args.device, lambda: decode(source))
            def encode_video():
                batches = []
                for start in range(0, len(frames), args.image_batch_size):
                    batch = torch.from_numpy(frames[start:start + args.image_batch_size]).permute(0, 3, 1, 2).to(args.device).float() / 255
                    batch = ((batch - mean) / std).to(encoder.visual.conv1.weight.dtype)
                    batches.append(encoder.encode_image(batch).float())
                raw = torch.cat(batches)
                features = F.normalize(raw, dim=-1, eps=1e-5)
                n = len(features)
                start = torch.arange(n, device=args.device, dtype=torch.float32) / n
                tef = torch.stack([start, start + 1.0 / n], dim=-1)
                return torch.cat([features, tef], dim=-1)
            features, encoding_ms = timed(args.device, encode_video)
            video_features[video_id] = (features, metadata)
            # Experimental artifact for repeatability, not the production cache of C7.
            np.savez_compressed(args.output / (video_id + '.npz'), features=features.cpu().numpy())
            feature_timings.append(dict(video_id=video_id, decode_ms=decode_ms, image_encode_ms=encoding_ms, **metadata))
            print(json.dumps({'phase': 'video_encoded', **feature_timings[-1]}), flush=True)
            del frames

        text_features = {}
        text_timings = []
        for row in rows:
            def encode_text():
                tokens = clip.tokenize(row['query'], truncate=False).to(args.device)
                length = int((tokens != 0).sum().item())
                if length > 32:
                    raise ValueError('Query exceeds the trained 32-token context')
                dtype = encoder.visual.conv1.weight.dtype
                x = encoder.token_embedding(tokens).to(dtype)
                x = x + encoder.positional_embedding.to(dtype)
                x = encoder.transformer(x.permute(1, 0, 2)).permute(1, 0, 2)
                x = encoder.ln_final(x).float()[:, :length]
                return F.normalize(x, dim=-1, eps=1e-5)
            encoded, elapsed = timed(args.device, encode_text)
            text_features[row['query_id']] = encoded
            text_timings.append({'query_id': row['query_id'], 'text_encode_ms': elapsed, 'tokens': encoded.shape[1]})

    prediction_path = args.output / 'predictions.jsonl'
    model_info = []
    with prediction_path.open('w', encoding='utf-8') as stream, torch.inference_mode():
        for name in ('qd_detr', 'cg_detr'):
            started = time.perf_counter()
            checkpoint = torch.load(args.models / ('author_' + name + '_clip.ckpt'), map_location='cpu', weights_only=False)
            original = checkpoint['opt']
            options = EasyDict(original if isinstance(original, dict) else vars(original))
            options.device = args.device
            # Original video-only checkpoints serialize this option as None.
            options.a_feat_dim = options.get('a_feat_dim') or 0
            builder = __import__('lighthouse.common.' + name, fromlist=['build_model']).build_model
            model, criterion = builder(options)
            model.load_state_dict(checkpoint['model'], strict=True)
            model.to(args.device).eval()
            model_info.append({'model': name, 'parameters': sum(p.numel() for p in model.parameters()),
                               'strict_load': True, 'checkpoint_epoch': checkpoint.get('epoch'),
                               'load_ms': round((time.perf_counter() - started) * 1000, 3)})
            del checkpoint, criterion
            gc.collect()
            for row in rows:
                features, metadata = video_features[row['target_video_id']]
                query = text_features[row['query_id']]
                inputs = {'src_vid': features.unsqueeze(0), 'src_vid_mask': torch.ones(1, len(features), device=args.device),
                          'src_txt': query, 'src_txt_mask': torch.ones(1, query.shape[1], device=args.device)}
                if name == 'cg_detr':
                    inputs.update(vid=None, qid=None)
                outputs, elapsed = timed(args.device, lambda: model(**inputs))
                scores = outputs['pred_logits'].softmax(-1)[0, :, 0]
                center, width = outputs['pred_spans'][0].unbind(-1)
                spans = torch.stack([center - width / 2, center + width / 2], dim=-1) * metadata['model_duration_s']
                spans = spans.clamp(min=0, max=metadata['duration_s'])
                ranked = sorted(torch.cat([spans, scores[:, None]], dim=-1).cpu().tolist(), key=lambda x: x[2], reverse=True)
                record = {'query_id': row['query_id'], 'query': row['query'],
                          'input_labels_sha256': labels_sha256,
                          'video_id': row['target_video_id'], 'model': name,
                          'grounding_ms': elapsed, 'windows': ranked,
                          'saliency': outputs['saliency_scores'][0].cpu().tolist()}
                stream.write(json.dumps(record) + '\n')
                stream.flush()
                print(json.dumps({'phase': 'grounded', 'model': name, 'query_id': row['query_id'], 'grounding_ms': elapsed, 'top_window': ranked[0]}), flush=True)
            del model
            gc.collect()
            if args.device == 'cuda':
                torch.cuda.empty_cache()
    summary = {
        'device': args.device, 'torch': torch.__version__, 'clip_load_ms': load_ms,
        'model_info': model_info, 'video_timings': feature_timings, 'text_timings': text_timings,
        'peak_process_rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
        'process_elapsed_s': round(time.perf_counter() - STARTED, 3),
        'preprocessing': 'author-aligned CLIP L2 normalization, token features, 2-second ffmpeg grid, display orientation before scale/crop; shared JIT CLIP encoder',
        'quality_label_status': ('human_verified_inputs_not_a_quality_score'
                                 if all(row.get('human_verified') is True for row in rows)
                                 else 'unverified_inputs_not_a_quality_score'),
        'input_labels_sha256': labels_sha256,
        'end_to_end_search_benchmarked': False,
    }
    if args.device == 'cuda':
        summary.update(gpu=torch.cuda.get_device_name(),
                       peak_cuda_allocated_mib=round(torch.cuda.max_memory_allocated() / 2**20, 2),
                       peak_cuda_reserved_mib=round(torch.cuda.max_memory_reserved() / 2**20, 2))
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'phase': 'completed', 'summary': str(args.output / 'summary.json')}), flush=True)


if __name__ == '__main__':
    main()
