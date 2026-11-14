# Temporal Search

Independent branch design for query-conditioned video moment retrieval.

Start with the Vietnamese [Group A dossier](../docs/temporal-search/README.md).
The existing search backend, frontend, model configuration and Compose stack
remain outside this directory and have not been changed by Group A.

Current artifacts:

- `contracts/openapi.json` — standalone OpenAPI 3.1 design, not a running API.
- `contracts/examples.json` — illustrative requests/responses, not measured output.
- `tools/legacy_baseline.py` — source checksum and optional local API snapshots.
- `tools/validate_contract.py` — schema/example and semantic consistency checks.

No application server, model dependency, container or training process is
implemented here yet. Runtime implementation follows the Group B feasibility
checks and subsequent Group C/D tasks.
