"""Integration tests for Auth API endpoints (/api/v1/auth)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from api.deps import get_current_user, require_admin
from api.main import app
from core.security import create_refresh_token
from db.models.review import User, UserRole


@pytest.fixture
def mock_user() -> User:
    """Fixture providing a mock engineer user."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "test.engineer@scenesearch.ai"
    user.display_name = "Test Engineer"
    user.role = UserRole.ENGINEER.value
    user.token_version = 0
    user.is_active = True
    user.password_hash = "$2b$12$MockHashedPasswordStringHere"
    return user


@pytest.fixture
def mock_admin() -> User:
    """Fixture providing a mock admin user."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "test.admin@scenesearch.ai"
    user.display_name = "Test Admin"
    user.role = UserRole.ADMIN.value
    user.token_version = 0
    user.is_active = True
    user.password_hash = "$2b$12$MockHashedPasswordStringHere"
    return user


@pytest.mark.asyncio
async def test_login_success(mock_user: User) -> None:
    """Test successful user login returning access and refresh tokens."""
    target_repo = "services.auth.UserRepository.get_by_email"
    with (
        patch(target_repo, new_callable=AsyncMock) as mock_get_by_email,
        patch("services.auth.verify_password", return_value=True),
    ):
        mock_get_by_email.return_value = mock_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": mock_user.email, "password": "ValidPassword123!"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == mock_user.email
        assert data["user"]["role"] == mock_user.role


@pytest.mark.asyncio
async def test_login_invalid_password(mock_user: User) -> None:
    """Test login failure on incorrect password."""
    target_repo = "services.auth.UserRepository.get_by_email"
    with (
        patch(target_repo, new_callable=AsyncMock) as mock_get_by_email,
        patch("services.auth.verify_password", return_value=False),
    ):
        mock_get_by_email.return_value = mock_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": mock_user.email, "password": "WrongPassword"},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect email or password"


@pytest.mark.asyncio
async def test_register_success(mock_user: User) -> None:
    """Test successful user registration."""
    repo_exists = "services.auth.UserRepository.exists_by_email"
    repo_create = "services.auth.UserRepository.create"
    with (
        patch(repo_exists, new_callable=AsyncMock) as exists_mock,
        patch(repo_create, new_callable=AsyncMock) as mock_create,
    ):
        exists_mock.return_value = False
        mock_create.return_value = mock_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": mock_user.email,
                    "password": "StrongPassword123!",
                    "display_name": "New Engineer",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == mock_user.email
        assert mock_create.await_args.kwargs["role"] == UserRole.ENGINEER.value


@pytest.mark.asyncio
async def test_register_rejects_client_supplied_role(mock_user: User) -> None:
    """Public registration must not allow callers to select a privileged role."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": mock_user.email,
                "password": "StrongPassword123!",
                "display_name": "Attacker",
                "role": "admin",
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_refresh_token_success(mock_user: User) -> None:
    """Test renewing token pair using a valid refresh token."""
    refresh_tok = create_refresh_token(subject=mock_user.id, role=mock_user.role)
    target_repo = "services.auth.UserRepository.get_by_id"

    with (
        patch(target_repo, new_callable=AsyncMock) as mock_get_by_id,
        patch("services.auth.is_token_blacklisted", return_value=False),
        patch("services.auth.blacklist_token", new_callable=AsyncMock),
    ):
        mock_get_by_id.return_value = mock_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_tok},
            )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_rejects_token_issued_before_password_change(mock_user: User) -> None:
    """A refresh token from before a password change must not create a new session."""
    refresh_tok = create_refresh_token(
        subject=mock_user.id,
        role=mock_user.role,
        token_version=mock_user.token_version,
    )
    mock_user.token_version += 1

    with (
        patch("services.auth.UserRepository.get_by_id", new_callable=AsyncMock) as mock_get_by_id,
        patch("services.auth.is_token_blacklisted", return_value=False),
    ):
        mock_get_by_id.return_value = mock_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_tok},
            )

    assert response.status_code == 401
    assert response.json()["detail"] == "Refresh token has been revoked"


@pytest.mark.asyncio
async def test_logout_endpoint(mock_user: User) -> None:
    """Test user logout with token blacklisting."""
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("services.auth.AuthService.logout_user", new_callable=AsyncMock) as mock_logout:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/auth/logout",
                    headers={"Authorization": "Bearer mock_access_token"},
                    json={"refresh_token": "mock_refresh_token"},
                )

            assert response.status_code == 200
            assert response.json()["message"] == "Successfully logged out"
            mock_logout.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_profile(mock_user: User) -> None:
    """Test updating user profile display name."""
    app.dependency_overrides[get_current_user] = lambda: mock_user

    repo_upd = "services.auth.UserRepository.update_profile"
    try:
        with patch(repo_upd, new_callable=AsyncMock) as mock_upd:
            mock_user.display_name = "Updated Name"
            mock_upd.return_value = mock_user

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.patch(
                    "/api/v1/auth/profile",
                    headers={"Authorization": "Bearer mock_token"},
                    json={"display_name": "Updated Name"},
                )

            assert response.status_code == 200
            assert response.json()["display_name"] == "Updated Name"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_change_password(mock_user: User) -> None:
    """Test changing password."""
    app.dependency_overrides[get_current_user] = lambda: mock_user
    repo_pass = "services.auth.UserRepository.update_password"

    try:
        with (
            patch("services.auth.verify_password", return_value=True),
            patch(repo_pass, new_callable=AsyncMock) as mock_upd,
        ):
            mock_upd.return_value = mock_user

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/auth/change-password",
                    headers={"Authorization": "Bearer mock_token"},
                    json={
                        "current_password": "OldPassword123!",
                        "new_password": "NewStrongPassword123!",
                    },
                )

            assert response.status_code == 200
            assert "Password changed" in response.json()["message"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_admin_list_users(mock_admin: User, mock_user: User) -> None:
    """Test admin list users endpoint."""
    app.dependency_overrides[require_admin] = lambda: mock_admin

    try:
        with (
            patch("services.auth.UserRepository.list_users", new_callable=AsyncMock) as mock_list,
            patch("services.auth.UserRepository.count_users", new_callable=AsyncMock) as mock_count,
        ):
            mock_list.return_value = [mock_admin, mock_user]
            mock_count.return_value = 2

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/v1/auth/users",
                    headers={"Authorization": "Bearer mock_admin_token"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2
            assert len(data["items"]) == 2
    finally:
        app.dependency_overrides.pop(require_admin, None)
