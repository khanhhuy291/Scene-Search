"""Create the local administrator explicitly: python -m services.bootstrap_admin."""

from __future__ import annotations

import asyncio
import os

from core.config import get_settings
from core.security import get_password_hash
from infrastructure.postgres import close_postgres, get_session_factory
from repositories.user import UserRepository


async def main() -> None:
    if get_settings().app.env != "development":
        raise RuntimeError("Local admin bootstrap requires APP_ENV=development")
    email = os.environ["LOCAL_ADMIN_EMAIL"]
    password = os.environ["LOCAL_ADMIN_PASSWORD"]
    if len(password) < 12:
        raise ValueError("LOCAL_ADMIN_PASSWORD must contain at least 12 characters")
    try:
        async with get_session_factory()() as session:
            repository = UserRepository(session)
            existing = await repository.get_by_email(email)
            if existing is not None:
                if existing.role != "admin":
                    raise RuntimeError(
                        "Existing account is not an admin; refusing to change its role"
                    )
                print(f"Local administrator already exists: {email}")
                return
            await repository.create(
                email=email,
                password_hash=get_password_hash(password),
                role="admin",
                display_name="Local Admin",
            )
            print(f"Created local administrator: {email}")
    finally:
        await close_postgres()


if __name__ == "__main__":
    asyncio.run(main())
