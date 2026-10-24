import hashlib
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.models.analysis import ImageExtractionResponse, TokenConfidence
from app.services.image_recognition import ImageRecognitionError, recognize_image

client = TestClient(app)


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 32), "white").save(output, format="PNG")
    return output.getvalue()


def test_image_extraction_endpoint_returns_provenanced_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_bytes = _png_bytes()

    def fake_recognize(
        payload: bytes,
        *,
        filename: str,
        media_type: str,
        hand_drawn: bool,
    ) -> ImageExtractionResponse:
        assert payload == image_bytes
        assert filename == "molecule.png"
        assert media_type == "image/png"
        assert hand_drawn is False
        return ImageExtractionResponse(
            candidate_smiles="CCO",
            model_version="test",
            source_sha256=hashlib.sha256(payload).hexdigest(),
            filename=filename,
            media_type="image/png",
            confidence_mean=0.95,
            confidence_min=0.9,
            token_confidences=[TokenConfidence(token="C", confidence=0.9)],
            warnings=["Verify the candidate."],
        )

    monkeypatch.setattr("app.api.routes.recognize_image", fake_recognize)
    response = client.post(
        "/api/extract/image",
        files={"image": ("molecule.png", image_bytes, "image/png")},
        data={"hand_drawn": "false"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_smiles"] == "CCO"
    assert body["method"] == "DECIMER-Image-Transformer"
    assert body["source_sha256"] == hashlib.sha256(image_bytes).hexdigest()


def test_invalid_image_has_specific_error() -> None:
    with pytest.raises(ImageRecognitionError) as caught:
        recognize_image(
            b"not an image",
            filename="bad.png",
            media_type="image/png",
        )
    assert caught.value.code == "INVALID_IMAGE"
    assert caught.value.status_code == 422


def test_unsupported_image_type_is_rejected_before_model_load() -> None:
    with pytest.raises(ImageRecognitionError) as caught:
        recognize_image(
            _png_bytes(),
            filename="molecule.gif",
            media_type="image/gif",
        )
    assert caught.value.code == "UNSUPPORTED_IMAGE_TYPE"
    assert caught.value.status_code == 415
