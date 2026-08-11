from pydantic import SecretStr

from core.config import DatabaseSettings
from infrastructure.postgres import database_url


def test_database_url_masks_password_in_string_representation() -> None:
    settings = DatabaseSettings(
        _env_file=None,
        host="database.internal",
        user="scene-user",
        password=SecretStr("secret:@/value"),
        database="scenes",
    )

    url = database_url(settings)

    assert url.password == "secret:@/value"
    assert "secret:@/value" not in str(url)
    assert "***" in str(url)


def test_database_url_parses_configured_url_as_masked_url() -> None:
    settings = DatabaseSettings(
        _env_file=None,
        DATABASE_URL="postgresql+asyncpg://scene-user:secret@database.internal/scenes",
    )

    url = database_url(settings)

    assert url.password == "secret"
    assert "secret" not in str(url)
