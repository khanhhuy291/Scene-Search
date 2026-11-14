# Temporal Search

Independent branch design for query-conditioned video moment retrieval.

Start with the Vietnamese [Group A dossier](../docs/temporal-search/README.md).
The existing search backend, frontend, model configuration and Compose stack
remain outside this directory and have not been changed by Group A.

Design artifacts:

- `contracts/openapi.json` — standalone OpenAPI 3.1 design, not a running API.
- `contracts/examples.json` — illustrative requests/responses, not measured output.
- `tools/legacy_baseline.py` — source checksum and optional local API snapshots.
- `tools/validate_contract.py` — schema/example and semantic consistency checks.

Research now includes a human-reviewed 120-pair evaluation set, legacy baseline
collector, checkpoint pilot, annotation review tools and a pinned source/weight
manifest. See the Vietnamese [research status](../docs/temporal-search/RESEARCH_STATUS.md).
The CPU pilot runs in an isolated temporary container; it is not a deployed
temporal search API. No training has been performed. The 20-pair pilot has now
been human reviewed and scored. The 100-pair expansion is also reviewed and
scored: 120 labels, 120 legacy responses and 240 QD/CG predictions in total.
See the [completed Group B evaluation](../docs/temporal-search/REVIEWED_EXPANSION_RESULTS.md).
Rebuild reports without rerunning models using
`python temporal-search/evaluation/summarize_group_b.py`.
