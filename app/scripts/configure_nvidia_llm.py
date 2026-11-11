#!/usr/bin/env python3
"""Set the NVIDIA hosted vision model key without echoing it or putting it in shell history."""

from __future__ import annotations

import os
import tempfile
from getpass import getpass
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
BASE_URL = "https://integrate.api.nvidia.com/v1"


def main() -> None:
    if not ENV_FILE.is_file():
        raise SystemExit(f"Missing {ENV_FILE}; create app/.env first.")

    key = getpass("NVIDIA API key (input hidden): ").strip()
    if not key:
        raise SystemExit("No key entered; app/.env was not changed.")

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    values = {
        "LLM_API_KEY": key,
        "LLM_BASE_URL": BASE_URL,
        "LLM_MODEL": MODEL,
    }
    found: set[str] = set()
    output: list[str] = []
    for line in lines:
        name = line.partition("=")[0]
        if name in values:
            output.append(f"{name}={values[name]}")
            found.add(name)
        else:
            output.append(line)
    output.extend(f"{name}={value}" for name, value in values.items() if name not in found)

    fd, temporary = tempfile.mkstemp(prefix=".env.", dir=ENV_FILE.parent, text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(output) + "\n")
        os.replace(temporary, ENV_FILE)
        os.chmod(ENV_FILE, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

    print(f"Configured {MODEL} in {ENV_FILE} (key hidden; file mode 600).")


if __name__ == "__main__":
    main()
