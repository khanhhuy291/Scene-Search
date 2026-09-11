"""Unit tests for Qwen/Qwen3-VL-Embedding-2B infrastructure, ML encoder, and summary pipeline."""

from unittest.mock import MagicMock

import pytest
from PIL import Image

from core.config import MLSettings, get_settings
from ml.encoder import get_encoder, reset_encoder
from ml.qwen_encoder import (
    QwenEmbeddingError,
    QwenVLEmbeddingClient,
    QwenVLEncoder,
    get_qwen_embedding_client,
    reset_qwen_embedding_client,
)
from pipelines.common.types import FrameRecord, SceneRecord
from pipelines.summary.summarizer import (
    build_scene_text_summary,
    embed_scene_summaries,
)


@pytest.fixture(autouse=True)
def clean_clients():
    reset_qwen_embedding_client()
    reset_encoder()
    get_settings.cache_clear()
    yield
    reset_qwen_embedding_client()
    reset_encoder()
    get_settings.cache_clear()


def test_qwen_client_initialization():
    client = QwenVLEmbeddingClient()
    assert client.dimension == 2048
    assert client.model_version == "qwen3-vl-embedding-2b-v1"


def test_qwen_client_singleton():
    c1 = get_qwen_embedding_client()
    c2 = get_qwen_embedding_client()
    assert c1 is c2


def test_qwen_client_normalize():
    client = QwenVLEmbeddingClient()
    unnorm = [[3.0, 4.0]]
    normed = client._normalize(unnorm)
    assert pytest.approx(normed[0][0]) == 0.6
    assert pytest.approx(normed[0][1]) == 0.8


def test_qwen_remote_client_sends_auth_and_uses_configured_timeout(monkeypatch):
    import sys

    settings = MagicMock()
    settings.qwen_embedding_url = "http://qwen-embedding:8001"
    settings.qwen_embedding_timeout = 300.0
    settings.qwen_embedding_api_key.get_secret_value.return_value = "internal-secret"
    client = QwenVLEmbeddingClient(settings=settings)
    response = MagicMock()
    response.json.return_value = {"embeddings": [[1.0] + [0.0] * 2047]}
    http_client = MagicMock()
    http_client.__enter__.return_value.post.return_value = response
    httpx = MagicMock()
    httpx.Client.return_value = http_client
    monkeypatch.setitem(sys.modules, "httpx", httpx)

    vectors = client.encode_texts(["red car"])

    httpx.Client.assert_called_once_with(timeout=300.0)
    _, kwargs = http_client.__enter__.return_value.post.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer internal-secret"}
    assert len(vectors[0]) == 2048


def test_qwen_client_sentence_transformer_mock():
    client = QwenVLEmbeddingClient()
    mock_st = MagicMock()
    mock_st.encode.return_value = [[0.6, 0.8]]
    client._st_model = mock_st

    img = Image.new("RGB", (10, 10))
    res_img = client.encode_images([img])
    assert res_img == [[0.6, 0.8]]
    mock_st.encode.assert_called_once()

    mock_st.reset_mock()
    res_txt = client.encode_texts(["hello"])
    assert res_txt == [[0.6, 0.8]]
    mock_st.encode.assert_called_once()


def test_qwen_client_load_error_raises_exception(monkeypatch):
    import sys

    client = QwenVLEmbeddingClient(settings=MLSettings(qwen_embedding_url=None))
    fake_st = MagicMock()
    fake_st.SentenceTransformer.side_effect = RuntimeError("Model download failed")
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_st)
    with pytest.raises(QwenEmbeddingError, match="Failed to load Qwen embedding model"):
        client.load()


def test_qwen_encoder_protocol():
    mock_client = MagicMock()
    mock_client.dimension = 2048
    mock_client.model_version = "qwen3-vl-embedding-2b-v1"
    mock_client.encode_images.return_value = [[0.1] * 2048]
    mock_client.encode_texts.return_value = [[0.2] * 2048]
    mock_client.encode_multimodal.return_value = [[0.3] * 2048]

    encoder = QwenVLEncoder(client=mock_client)
    assert encoder.dimension == 2048
    assert encoder.model_version == "qwen3-vl-embedding-2b-v1"

    img = Image.new("RGB", (10, 10))
    imgs_out = encoder.encode_images([img])
    assert imgs_out == [[0.1] * 2048]

    txts_out = encoder.encode_texts(["test text"])
    assert txts_out == [[0.2] * 2048]

    multi_out = encoder.encode_multimodal([img], ["test text"])
    assert multi_out == [[0.3] * 2048]


def test_get_encoder_qwen_selection(monkeypatch):
    monkeypatch.setenv("ML_ENCODER_NAME", "Qwen/Qwen3-VL-Embedding-2B")
    monkeypatch.setenv("QDRANT_VECTOR_SIZE", "2048")
    get_settings.cache_clear()
    reset_encoder()
    encoder = get_encoder()
    assert isinstance(encoder, QwenVLEncoder)


def test_build_scene_text_summary():
    frame = FrameRecord(timestamp_ms=1000, frame_index=0, image=Image.new("RGB", (10, 10)))
    scene = SceneRecord(
        scene_id="s1",
        video_id="v1",
        start_ms=1000,
        end_ms=6000,
        keyframes=[frame],
    )

    summary_text = build_scene_text_summary(scene)
    assert "Scene duration 1.0s to 6.0s." in summary_text
    assert "Contains 1 keyframes." in summary_text


def test_embed_scene_summaries():
    mock_client = MagicMock()
    mock_client.settings.qwen_model_name = "Qwen/Qwen3-VL-Embedding-2B"
    mock_client.model_version = "qwen3-vl-embedding-2b-v1"
    mock_client.encode_multimodal.return_value = [[0.5] * 2048]

    img = Image.new("RGB", (10, 10))
    frame = FrameRecord(timestamp_ms=0, frame_index=0, image=img)
    scene = SceneRecord(
        scene_id="s1",
        video_id="v1",
        start_ms=0,
        end_ms=5000,
        keyframes=[frame],
    )

    records = embed_scene_summaries([scene], client=mock_client)
    assert len(records) == 1
    assert records[0].scene_id == "s1"
    assert records[0].video_id == "v1"
    assert len(records[0].embedding) == 2048
    assert records[0].model_name == "Qwen/Qwen3-VL-Embedding-2B"
