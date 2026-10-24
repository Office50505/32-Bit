from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.models.analysis import ImageExtractionResponse, TokenConfidence

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
SUPPORTED_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp"}
_INFERENCE_LOCK = threading.Lock()


class ImageRecognitionError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        technical_detail: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.technical_detail = technical_detail


@dataclass(frozen=True)
class _Recognizer:
    predict: Callable[..., Any]
    version: str


@lru_cache(maxsize=1)
def _load_recognizer() -> _Recognizer:
    try:
        module = importlib.import_module("DECIMER")
        predictor = module.predict_SMILES
        version = importlib.metadata.version("decimer")
    except Exception as exc:  # Import also loads the pinned DECIMER model files.
        raise ImageRecognitionError(
            503,
            "EXTRACTION_ENGINE_UNAVAILABLE",
            "DECIMER could not be loaded. Install the backend image-recognition "
            "dependencies and restart the API.",
            type(exc).__name__,
        ) from exc
    return _Recognizer(predict=predictor, version=version)


def _decode_image(image_bytes: bytes) -> np.ndarray:
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            width, height = source.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise ImageRecognitionError(
                    413,
                    "IMAGE_DIMENSIONS_EXCEEDED",
                    "The image dimensions are too large. Use an image with at most "
                    "25 million pixels.",
                )
            source.load()
            return np.asarray(source.convert("RGB"))
    except ImageRecognitionError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageRecognitionError(
            422,
            "INVALID_IMAGE",
            "The uploaded file is not a readable PNG, JPEG, or WebP image.",
            type(exc).__name__,
        ) from exc


def _normalise_prediction(prediction: Any) -> tuple[str, list[TokenConfidence]]:
    if isinstance(prediction, tuple) and len(prediction) == 2:
        smiles, raw_confidences = prediction
    else:
        smiles, raw_confidences = prediction, []

    candidate = str(smiles).strip()
    if not candidate:
        raise ImageRecognitionError(
            422,
            "NO_STRUCTURE_RECOGNIZED",
            "DECIMER did not recognize a molecular structure in this image.",
        )

    confidences: list[TokenConfidence] = []
    for item in raw_confidences or []:
        try:
            token, value = item
            confidence = max(0.0, min(1.0, float(value)))
            confidences.append(TokenConfidence(token=str(token), confidence=confidence))
        except (TypeError, ValueError):
            continue
    return candidate, confidences


def recognize_image(
    image_bytes: bytes,
    *,
    filename: str,
    media_type: str,
    hand_drawn: bool = False,
) -> ImageExtractionResponse:
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise ImageRecognitionError(
            415,
            "UNSUPPORTED_IMAGE_TYPE",
            "Photo recognition accepts PNG, JPEG, or WebP images only.",
        )
    if not image_bytes:
        raise ImageRecognitionError(422, "EMPTY_IMAGE", "The uploaded image is empty.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ImageRecognitionError(
            413,
            "IMAGE_TOO_LARGE",
            "The uploaded image exceeds the 5 MB limit.",
        )

    image = _decode_image(image_bytes)
    recognizer = _load_recognizer()
    try:
        with _INFERENCE_LOCK:
            prediction = recognizer.predict(image, confidence=True, hand_drawn=hand_drawn)
    except ImageRecognitionError:
        raise
    except Exception as exc:
        raise ImageRecognitionError(
            502,
            "EXTRACTION_FAILED",
            "DECIMER could not produce a candidate from this image. "
            "Try a tighter, higher-contrast crop.",
            type(exc).__name__,
        ) from exc

    candidate, token_confidences = _normalise_prediction(prediction)
    values = [item.confidence for item in token_confidences]
    warnings = [
        "Image recognition can be wrong. Compare the candidate with the source before analysis.",
    ]
    if values and min(values) < 0.5:
        warnings.append(
            "At least one token has low recognition confidence; inspect the candidate carefully."
        )

    return ImageExtractionResponse(
        candidate_smiles=candidate,
        model_version=recognizer.version,
        source_sha256=hashlib.sha256(image_bytes).hexdigest(),
        filename=Path(filename).name or "uploaded-image",
        media_type=media_type,
        confidence_mean=sum(values) / len(values) if values else None,
        confidence_min=min(values) if values else None,
        token_confidences=token_confidences,
        warnings=warnings,
    )
