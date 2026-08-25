#!/bin/sh
# Create the object-storage buckets and make sure none of them is public.
#
# Three buckets exist, and the separation is the privacy mechanism (ADR-0003):
#
#   $MINIO_BUCKET          general application objects
#   $MINIO_RAW_BUCKET      original frames and clips; never presigned, never served
#   $MINIO_DERIVED_BUCKET  anonymized thumbnails and preview clips; short-TTL URLs
#
# "anonymous set none" is applied to every bucket including the derived one.
# Derived assets are anonymized, but they are still driving footage and are
# reachable only through a short-lived presigned URL, never by guessing a path.
set -eu

MINIO_BUCKET="${MINIO_BUCKET:-scenesearch}"
MINIO_RAW_BUCKET="${MINIO_RAW_BUCKET:-scenesearch-raw}"
MINIO_DERIVED_BUCKET="${MINIO_DERIVED_BUCKET:-scenesearch-derived}"

if [ "$MINIO_RAW_BUCKET" = "$MINIO_DERIVED_BUCKET" ]; then
    echo "MINIO_RAW_BUCKET and MINIO_DERIVED_BUCKET must differ; sharing one" >&2
    echo "bucket would make originals presignable." >&2
    exit 1
fi

mc alias set local http://minio:9000 "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY"

for bucket in "$MINIO_BUCKET" "$MINIO_RAW_BUCKET" "$MINIO_DERIVED_BUCKET"; do
    mc mb --ignore-existing "local/$bucket"
    mc anonymous set none "local/$bucket"
    echo "ready: $bucket"
done
