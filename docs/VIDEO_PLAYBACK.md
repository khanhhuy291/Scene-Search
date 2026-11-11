# Full-video playback and segment boundaries

Ingestion stores one complete playable video per source. Search still indexes
segments, but playback opens the complete video, seeks to `ts_start_s`, and pauses
at `ts_end_s`. Search cards and chat use the same segment playback helpers.
Pressing play again after the segment ends seeks back to its start.

## Object layout

```text
scenesearch-raw/
  <video_id>.mov                         # untouched original upload

scenesearch-derived/
  videos/<video_id>/
    playback.mp4                        # one complete video, shared by all segments
    segments/<segment_id>/
      thumbnail.jpg                     # representative sampled frame
```

Each Qdrant segment point stores its own source-timeline start/end, thumbnail key,
and the shared full-video key. No segment MP4 is generated. A one-sample segment
includes at least one sampling interval; the end is exclusive and playback clamps
it to the actual source duration.

BDD100K H.264 MOV is remuxed to MP4 with fast-start metadata, preserving every
video packet and source timing. AAC audio, if present, is also remuxed. Other video
codecs use H.264 transcoding at source cadence; that fallback currently carries
video only. Retrieval sampling/deduplication never removes frames from playback.

Playback preserves the original source imagery: it is **not anonymized**. Payload
fields `playback_timeline="source"` and `playback_anonymized=false` describe this
explicitly. The media proxy reads derived storage rather than exposing raw bucket
objects. Thumbnail privacy remains subject to the existing ingestion detector.

The current dataset ZIP export includes complete unique videos and the selected
segment timestamps in the manifest; it does not cut a new MP4 per selected segment.

## Deletion

`DELETE /api/v1/videos/<video_id>` deletes the exact raw object recorded in the DB,
the new `videos/<video_id>/` tree, and the old flat preview/thumbnail layouts. It
also deletes video vectors/DB rows and clears API media/catalog caches.

The ten earlier test videos were deleted by their manifest IDs, and their task
history/cache was separately cleaned. Their local source files were preserved.
Audit files are under `data/ingestion/`:

- `deleted_test_batch.json`: IDs and deletion verification.
- `bdd100k_train_00.deleted-20261111.json`: archived original uploader manifest.
- `bdd100k_train_00.json`: fresh manifest, ready to ingest the first ten again.
- `playback_real_source_verification.json`: source/remux frame counts and timing.
- `playback_http_verification.json`: actual HTTP range checks.

## Verification

51 backend tests and 12 frontend tests passed. The real BDD sample
`0000f77c-6257be58.mov` retains all 1,217 frames, duration 40.366667 seconds, and
last-frame timestamp 40.333333 seconds after remux. Playback tests cover seek to
12 seconds, pause/clamp at 18 seconds, replay, and duration clamping.

After ingesting again, refresh the web page (Ctrl+Shift+R). The MinIO layout will
contain one `videos/<video_id>/` tree for each video, with segment subdirectories.
