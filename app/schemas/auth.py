"""Pydantic schemas for authentication, token refresh, profile, and user management."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from db.models.review import UserRole


class LoginRequest(BaseModel):
    """Payload for user login."""

    email: EmailStr
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    """Payload for registering a new user."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must have at least 8 characters")
    display_name: str | None = Field(default=None, max_length=128)


class RefreshTokenRequest(BaseModel):
    """Payload for renewing an expired access token."""

    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    """Optional payload for logout specifying refresh token to revoke."""

    refresh_token: str | None = None


class ChangePasswordRequest(BaseModel):
    """Payload for updating user password."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(
        ..., min_length=8, description="New password must have at least 8 characters"
    )


class UpdateProfileRequest(BaseModel):
    """Payload for updating user profile attributes."""

    display_name: str = Field(..., min_length=1, max_length=128)


class UpdateUserRoleRequest(BaseModel):
    """Payload for admin updating user role."""

    role: UserRole


class UpdateUserStatusRequest(BaseModel):
    """Payload for admin updating user active/inactive status."""

    is_active: bool


class UserRead(BaseModel):
    """Public representation of a user."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str | None = None
    role: UserRole
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """Token response returned on authentication or refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


class UserListResponse(BaseModel):
    """Paginated list of users for administration."""

    items: list[UserRead]
    total: int


__all__ = [
    "ChangePasswordRequest",
    "LoginRequest",
    "LogoutRequest",
    "MessageResponse",
    "RefreshTokenRequest",
    "RegisterRequest",
    "TokenResponse",
    "UpdateProfileRequest",
    "UpdateUserRoleRequest",
    "UpdateUserStatusRequest",
    "UserListResponse",
    "UserRead",
]
