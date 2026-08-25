"""Contract tests for the internal Qwen embedding HTTP service."""

import base64
import io
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError

from core.config import MLSettings
from ml import embedding_api


@pytest.fixture(autouse=True)
def reset_model_state():
    embedding_api._state = "unloaded"
    embedding_api._last_error = None
    embedding_api._active_requests = 0
    yield
    embedding_api._state = "unloaded"
    embedding_api._last_error = None
    embedding_api._active_requests = 0


def _encoded_image() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_request_validates_mode_inputs() -> None:
    with pytest.raises(ValidationError):
        embedding_api.EmbeddingRequest(mode="text", images=[_encoded_image()])
    with pytest.raises(ValidationError):
        embedding_api.EmbeddingRequest(mode="multimodal", texts=["one"], images=[])


def test_encode_image_decodes_and_closes_input(monkeypatch) -> None:
    client = MagicMock()
    client.encode_images.return_value = [[0.0] * 2048]
    monkeypatch.setattr(embedding_api, "get_qwen_embedding_client", lambda: client)
    embedding_api._state = "ready"
    request = embedding_api.EmbeddingRequest(mode="image", images=[_encoded_image()])

    vectors = embedding_api._encode(request)

    assert len(vectors[0]) == 2048
    image = client.encode_images.call_args.args[0][0]
    with pytest.raises(ValueError, match="closed"):
        image.getpixel((0, 0))


def test_inference_requires_explicit_model_load() -> None:
    request = embedding_api.EmbeddingRequest(mode="text", texts=["red car"])

    with pytest.raises(embedding_api.ModelNotReadyError, match="load it first"):
        embedding_api._encode(request)


def test_load_and_unload_model_lifecycle(monkeypatch) -> None:
    client = MagicMock()
    monkeypatch.setattr(embedding_api, "get_qwen_embedding_client", lambda: client)

    loaded = embedding_api._load_model()
    unloaded = embedding_api._unload_model()

    assert loaded.state == "ready"
    assert unloaded.state == "unloaded"
    client.load.assert_called_once_with()
    client.unload.assert_called_once_with()


def test_unload_refuses_active_inference() -> None:
    embedding_api._state = "busy"
    embedding_api._active_requests = 1

    with pytest.raises(embedding_api.ModelBusyError, match="busy"):
        embedding_api._unload_model()


def test_authorize_rejects_wrong_key(monkeypatch) -> None:
    settings = MagicMock()
    settings.ml.qwen_embedding_api_key.get_secret_value.return_value = "correct"
    monkeypatch.setattr(embedding_api, "get_settings", lambda: settings)

    with pytest.raises(HTTPException) as exc:
        embedding_api._authorize("Bearer wrong", None)

    assert exc.value.status_code == 401


def test_qwen_endpoint_settings_accept_unprefixed_environment(monkeypatch) -> None:
    monkeypatch.setenv("QWEN_EMBEDDING_URL", "http://qwen-embedding:8001")
    monkeypatch.setenv("QWEN_EMBEDDING_API_KEY", "secret")
    monkeypatch.setenv("QWEN_EMBEDDING_TIMEOUT", "300")

    settings = MLSettings()

    assert settings.qwen_embedding_url == "http://qwen-embedding:8001"
    assert settings.qwen_embedding_api_key is not None
    assert settings.qwen_embedding_api_key.get_secret_value() == "secret"
    assert settings.qwen_embedding_timeout == 300
