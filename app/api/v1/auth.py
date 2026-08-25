"""Authentication API routes for login, token refresh, logout, profile, and user management."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db_session, http_bearer, require_admin
from db.models.review import User
from schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UpdateUserRoleRequest,
    UpdateUserStatusRequest,
    UserListResponse,
    UserRead,
)
from services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate user and issue JWT access and refresh tokens",
)
async def login(
    request: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """Log in with email and password to receive an access token and refresh token."""
    auth_service = AuthService(db)
    user = await auth_service.authenticate_user(request.email, request.password)
    return auth_service.issue_token_for_user(user)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    request: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """Create a new user account and immediately issue access and refresh tokens."""
    auth_service = AuthService(db)
    user = await auth_service.register_user(request)
    return auth_service.issue_token_for_user(user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Renew access token using a valid refresh token",
)
async def refresh_token(
    request: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """Issue a new access token and rotate the refresh token."""
    auth_service = AuthService(db)
    return await auth_service.refresh_tokens(request.refresh_token)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke current token session",
)
async def logout(
    request: LogoutRequest | None,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(http_bearer)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[User, Depends(get_current_user)],
) -> MessageResponse:
    """Log out by invalidating the bearer access token and optional refresh token."""
    auth_service = AuthService(db)
    refresh_tok = request.refresh_token if request else None
    await auth_service.logout_user(credentials.credentials, refresh_tok)
    return MessageResponse(message="Successfully logged out")


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get current authenticated user profile",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserRead:
    """Fetch profile information for the currently authenticated user."""
    return UserRead.model_validate(current_user)


@router.patch(
    "/profile",
    response_model=UserRead,
    summary="Update profile details of current user",
)
async def update_profile(
    request: UpdateProfileRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRead:
    """Update display name for the authenticated user profile."""
    auth_service = AuthService(db)
    updated_user = await auth_service.update_profile(current_user, request.display_name)
    return UserRead.model_validate(updated_user)


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Change password for current user",
)
async def change_password(
    request: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """Update user password after validating current password."""
    auth_service = AuthService(db)
    await auth_service.change_password(current_user, request.current_password, request.new_password)
    return MessageResponse(message="Password changed successfully")


# --- Admin User Management Endpoints ---


@router.get(
    "/users",
    response_model=UserListResponse,
    summary="List all users (Admin only)",
)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[User, Depends(require_admin)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> UserListResponse:
    """Paginated list of all users in the system."""
    auth_service = AuthService(db)
    users, total = await auth_service.list_users(limit=limit, offset=offset)
    return UserListResponse(
        items=[UserRead.model_validate(u) for u in users],
        total=total,
    )


@router.patch(
    "/users/{user_id}/role",
    response_model=UserRead,
    summary="Update user role (Admin only)",
)
async def update_user_role(
    user_id: UUID,
    request: UpdateUserRoleRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[User, Depends(require_admin)],
) -> UserRead:
    """Update role for a specified user."""
    auth_service = AuthService(db)
    updated_user = await auth_service.update_user_role(user_id, request.role)
    return UserRead.model_validate(updated_user)


@router.patch(
    "/users/{user_id}/status",
    response_model=UserRead,
    summary="Activate or deactivate a user (Admin only)",
)
async def update_user_status(
    user_id: UUID,
    request: UpdateUserStatusRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[User, Depends(require_admin)],
) -> UserRead:
    """Update active/inactive status for a specified user."""
    auth_service = AuthService(db)
    updated_user = await auth_service.update_user_status(user_id, request.is_active)
    return UserRead.model_validate(updated_user)


__all__ = ["router"]
