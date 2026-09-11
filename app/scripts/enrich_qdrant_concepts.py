"""Offline Enrichment Script: Pre-extract present_concepts and absent_concepts for Qdrant.

Iterates over the Qdrant keyframe collection in batches, computes the NegEx polarities
for all canonical concepts, and updates the Qdrant payload with:
  - `present_concepts`: list[str]
  - `absent_concepts`: list[str]
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from core.config import get_settings
from search.catalog import keyframe_from_payload, structured_polarity
from search.query import concept_names, resolve_concept, split_clauses


def extract_point_concepts(point_id: str, payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Extract present and absent concepts from a keyframe's payload and caption."""
    keyframe = keyframe_from_payload(point_id, payload)
    if keyframe is None:
        return [], []

    clauses = split_clauses(keyframe.caption) if keyframe.caption else ()
    all_concepts = concept_names()

    present: list[str] = []
    absent: list[str] = []

    for concept in all_concepts:
        caption_pol, _ = resolve_concept(clauses, concept) if clauses else ("unknown", 0)
        struct_pol = structured_polarity(keyframe, concept)

        if struct_pol == "present" or (struct_pol != "absent" and caption_pol == "present"):
            present.append(concept)
        elif struct_pol == "absent" or caption_pol == "absent":
            absent.append(concept)

    # Also extract retrieval_tags into present concepts if applicable
    for tag in keyframe.retrieval_tags:
        normalized_tag = tag.lower().replace("-", "_").replace(" ", "_")
        if (
            normalized_tag in all_concepts
            and normalized_tag not in present
            and normalized_tag not in absent
        ):
            present.append(normalized_tag)

    return present, absent


async def enrich_collection(batch_size: int = 500) -> None:
    import httpx

    settings = get_settings()
    collection = settings.qdrant.collection
    qdrant_url = settings.qdrant.url or f"https://{settings.qdrant.host}:{settings.qdrant.port}"
    api_key = settings.qdrant.api_key.get_secret_value() if settings.qdrant.api_key else ""

    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
    }

    print(f"Starting high-speed enrichment on Qdrant collection: {collection} at {qdrant_url}")
    start_time = time.perf_counter()

    async with httpx.AsyncClient(
        headers=headers, verify=False, timeout=60.0, limits=httpx.Limits(max_connections=50)
    ) as client:
        # 1. Create Payload Indexes on present_concepts and absent_concepts
        indexes = {
            "present_concepts": "keyword",
            "absent_concepts": "keyword",
        }
        for field_name, schema_type in indexes.items():
            url = f"{qdrant_url}/collections/{collection}/index"
            body = {"field_name": field_name, "field_schema": schema_type}
            try:
                resp = await client.put(url, json=body)
                res = resp.json()
                print(f"Created payload index for {field_name}: {res.get('status')}")
            except Exception as exc:
                print(f"Index {field_name}: {exc}")

        # 2. Scroll through collection and update payloads concurrently
        offset: Any = None
        total_processed = 0
        total_present_tags = 0
        total_absent_tags = 0

        async def update_single(item: dict[str, Any]) -> None:
            single_set_url = f"{qdrant_url}/collections/{collection}/points/payload?wait=false"
            single_body = {"payload": item["payload"], "points": [item["id"]]}
            await client.post(single_set_url, json=single_body)

        while True:
            scroll_url = f"{qdrant_url}/collections/{collection}/points/scroll"
            scroll_body = {
                "limit": batch_size,
                "with_payload": True,
                "with_vector": False,
            }
            if offset is not None:
                scroll_body["offset"] = offset

            resp = await client.post(scroll_url, json=scroll_body)
            data = resp.json()
            result = data.get("result", {})
            points = result.get("points", [])
            offset = result.get("next_page_offset")

            if not points:
                break

            # Compute concepts for this batch
            points_to_update = []
            for p in points:
                pid = str(p["id"])
                payload = p.get("payload") or {}
                present, absent = extract_point_concepts(pid, payload)
                total_present_tags += len(present)
                total_absent_tags += len(absent)

                points_to_update.append(
                    {
                        "id": pid,
                        "payload": {
                            "present_concepts": present,
                            "absent_concepts": absent,
                        },
                    }
                )

            # Fire concurrent updates in chunks of 50
            chunk_size = 50
            for i in range(0, len(points_to_update), chunk_size):
                chunk = points_to_update[i : i + chunk_size]
                await asyncio.gather(*(update_single(item) for item in chunk))

            total_processed += len(points)
            elapsed = time.perf_counter() - start_time
            print(f"Processed {total_processed} points ({elapsed:.1f}s)...")

            if offset is None:
                break

    total_time = time.perf_counter() - start_time
    print(f"\n[DONE] Enriched {total_processed} keyframes in {total_time:.2f}s.")
    print(f"Total present concepts mapped: {total_present_tags}")
    print(f"Total absent concepts mapped: {total_absent_tags}")


if __name__ == "__main__":
    asyncio.run(enrich_collection())
