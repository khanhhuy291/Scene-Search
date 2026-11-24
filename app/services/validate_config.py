"""Check deployment env keys and typed settings without printing secret values."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from dotenv import dotenv_values
from pydantic import AliasChoices, ValidationError

from core.config import APP_ENV_FILE, Settings

# Consumed by Compose or the explicit admin bootstrap, rather than Settings.
DEPLOYMENT_KEYS = {
    "COMPOSE_PROJECT_NAME",
    "HTTP_BIND_ADDRESS",
    "HTTP_PORT",
    "QWEN_EMBEDDING_BATCH_SIZE",
    "LOCAL_ADMIN_EMAIL",
    "LOCAL_ADMIN_PASSWORD",
}


def settings_groups():
    return {name: field.annotation for name, field in Settings.model_fields.items()}


def supported_keys() -> set[str]:
    keys = set(DEPLOYMENT_KEYS)
    for group in settings_groups().values():
        prefix = group.model_config.get("env_prefix", "")
        for name, field in group.model_fields.items():
            alias = field.validation_alias
            if isinstance(alias, AliasChoices):
                keys.update(choice for choice in alias.choices if isinstance(choice, str))
            elif isinstance(alias, str):
                keys.add(alias)
            else:
                keys.add(f"{prefix}{name}".upper())
    return keys


def key_errors(path: Path) -> list[str]:
    values = dotenv_values(path)
    errors = [f"Unknown variable: {key}" for key in sorted(set(values) - supported_keys())]
    seen = set()
    for line in path.read_text().splitlines():
        match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match:
            key = match[1]
            if key in seen:
                errors.append(f"Duplicate variable: {key}")
            seen.add(key)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=APP_ENV_FILE)
    args = parser.parse_args()
    if not args.env_file.is_file():
        print("Env file missing; copy app/.env.example to app/.env and configure credentials.")
        return 1
    errors = key_errors(args.env_file)
    try:
        groups = {name: model(_env_file=args.env_file) for name, model in settings_groups().items()}
        Settings(_env_file=None, **groups)
    except ValidationError as exc:
        # Pydantic's default repr can contain credentials/URLs: print locations only.
        errors.extend(
            f"Invalid setting: {'.'.join(map(str, error['loc']))} ({error['type']})"
            for error in exc.errors(include_input=False)
        )
    for error in errors:
        print(error)
    if errors:
        return 1
    print("Configuration valid: env keys and typed settings checked; no services contacted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
