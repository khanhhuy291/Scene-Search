#!/usr/bin/env bash
# Run interactively on the host: bash app/scripts/recover_local_cuda.sh
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE=(docker compose --env-file "$PROJECT_ROOT/app/.env" -f "$PROJECT_ROOT/docker-compose.local.yml")

echo "This reloads only NVIDIA UVM and recreates the local embedding container."
echo "Video data, databases and model cache are preserved."
sudo -v
"${COMPOSE[@]}" stop embedding-api
# Never force-unload a module. If another CUDA application holds UVM, stop that
# application before rerunning this script.
sudo modprobe -r nvidia_uvm
sudo modprobe nvidia_uvm
"${COMPOSE[@]}" up -d --no-deps --force-recreate embedding-api
"${COMPOSE[@]}" exec -T embedding-api python -u - <<'PY'
import json
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

import torch
from core.config import get_settings

assert torch.cuda.is_available(), "CUDA still cannot initialize; inspect the host driver"
assert (torch.ones(4, device="cuda") * 2).sum().item() == 8
print("CUDA kernel passed on", torch.cuda.get_device_name(0), flush=True)
key = get_settings().ml.qwen_embedding_api_key.get_secret_value()
last = None
for _ in range(120):
    try:
        request = Request("http://localhost:8001/model/status", headers={"Authorization": "Bearer " + key})
        with urlopen(request, timeout=10) as response:
            status = json.loads(response.read())
    except URLError:
        time.sleep(2)
        continue
    if status["state"] != last:
        print("Embedding model:", status["state"], flush=True)
        last = status["state"]
    if status["state"] == "error":
        raise RuntimeError(status.get("error"))
    if status["state"] == "ready":
        allocated = status.get("gpu_memory_allocated_mb")
        assert allocated and allocated > 100, "Model reports ready without GPU allocations"
        print("Model ready on GPU; allocated MiB:", allocated, flush=True)
        break
    time.sleep(2)
else:
    raise RuntimeError("Timed out waiting for the GPU model to load")
PY
echo "CUDA recovery verified. Resume with --retry-failed."
