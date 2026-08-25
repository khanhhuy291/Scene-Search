"""Repository for user data persistence and administration."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.review import User


class UserRepository:
    """Persistence boundary for User model operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Fetch user by primary UUID."""
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Fetch user by lowercase email address."""
        result = await self._session.execute(
            select(User).where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none()

    async def exists_by_email(self, email: str) -> bool:
        """Check if a user with the given email already exists."""
        user = await self.get_by_email(email)
        return user is not None

    async def create(
        self,
        email: str,
        password_hash: str,
        role: str,
        display_name: str | None = None,
        is_active: bool = True,
    ) -> User:
        """Create and persist a new user record."""
        user = User(
            email=email.lower().strip(),
            password_hash=password_hash,
            role=role,
            display_name=display_name,
            is_active=is_active,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def update_password(self, user: User, password_hash: str) -> User:
        """Update password and invalidate every token issued before this change."""
        user.password_hash = password_hash
        user.token_version += 1
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def update_profile(self, user: User, display_name: str | None) -> User:
        """Update display name for a user."""
        user.display_name = display_name
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def update_role(self, user: User, role: str) -> User:
        """Update role for a user."""
        user.role = role
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def update_status(self, user: User, is_active: bool) -> User:
        """Update active/inactive status for a user."""
        user.is_active = is_active
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def count_users(self) -> int:
        """Count total registered users."""
        result = await self._session.execute(select(func.count()).select_from(User))
        return result.scalar_one() or 0

    async def list_users(self, limit: int = 50, offset: int = 0) -> list[User]:
        """List users with pagination."""
        result = await self._session.execute(
            select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())


__all__ = ["UserRepository"]
