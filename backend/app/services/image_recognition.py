from __future__ import annotations

import hashlib
import json
import os
import select
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

from PIL import Image, UnidentifiedImageError

from app.models.analysis import ExtractionEngineStatus, ImageExtractionResponse

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
SUPPORTED_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp"}
MODEL_VERSION = "1.0.0+6f6502b"
MODEL_SIZE = 1_134_334_833
MODEL_SHA256 = "5990bc19aaafa5cf44e9d04e06fb8e2b5aea50c66e1e925f662bdff7d2a6422c"
EngineStage = Literal["not_ready", "downloading", "extracting", "loading", "ready", "error"]


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


@dataclass
class _Progress:
    stage: EngineStage = "not_ready"
    message: str = "MolNexTR is installed but its model has not been loaded yet."
    bytes_downloaded: int = 0
    error_code: str | None = None
    technical_detail: str | None = None


class _MolNexTRWorker:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self._request_lock = threading.Lock()
        self._stderr_tail: deque[str] = deque(maxlen=30)
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    @classmethod
    def start(
        cls,
        *,
        python_path: Path,
        source_root: Path,
        model_root: Path,
        worker_path: Path,
    ) -> _MolNexTRWorker:
        environment = os.environ.copy()
        current_python_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = os.pathsep.join(
            value for value in (str(source_root), current_python_path) if value
        )
        environment["PYSTOW_HOME"] = str(model_root)
        environment["MOLNEXTR_DEBUG"] = "WARNING"
        environment.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        process = subprocess.Popen(
            [str(python_path), "-u", str(worker_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=environment,
        )
        worker = cls(process)
        message = worker._read_message(timeout=300)
        if message.get("event") != "ready":
            worker.close()
            raise RuntimeError(str(message.get("error") or "MolNexTR did not become ready"))
        return worker

    def predict(self, image_path: Path) -> dict[str, Any]:
        with self._request_lock:
            if self.process.poll() is not None:
                raise RuntimeError(self._failure_detail("MolNexTR worker stopped unexpectedly"))
            assert self.process.stdin is not None
            self.process.stdin.write(
                json.dumps({"action": "predict", "image_path": str(image_path)}) + "\n"
            )
            self.process.stdin.flush()
            message = self._read_message(timeout=240)
            if message.get("event") != "prediction":
                raise RuntimeError(str(message.get("error") or "MolNexTR prediction failed"))
            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("MolNexTR returned an invalid response")
            return result

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()

    def _read_message(self, *, timeout: int) -> dict[str, Any]:
        assert self.process.stdout is not None
        readable, _, _ = select.select([self.process.stdout], [], [], timeout)
        if not readable:
            raise RuntimeError(self._failure_detail("MolNexTR worker timed out"))
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(self._failure_detail("MolNexTR worker exited without a response"))
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"MolNexTR returned invalid JSON: {line[:200]}") from exc
        if not isinstance(message, dict):
            raise RuntimeError("MolNexTR returned a non-object response")
        return message

    def _drain_stderr(self) -> None:
        if self.process.stderr is None:
            return
        for line in self.process.stderr:
            self._stderr_tail.append(line.rstrip())

    def _failure_detail(self, summary: str) -> str:
        details = " | ".join(self._stderr_tail)
        return f"{summary}: {details}" if details else summary


class _ModelManager:
    def __init__(self, repository_root: Path | None = None) -> None:
        root = repository_root or Path(__file__).resolve().parents[3]
        self.python_path = Path(
            os.environ.get("PROVENANCELAB_MOLNEXTR_PYTHON", root / ".data/molnextr-venv/bin/python")
        )
        self.source_root = Path(
            os.environ.get("PROVENANCELAB_MOLNEXTR_SOURCE", root / ".data/MolNexTR")
        )
        self.model_root = Path(
            os.environ.get("PROVENANCELAB_MOLNEXTR_DATA", root / ".data")
        )
        self.model_path = self.model_root / "molnextr/molnextr_best.pth"
        self.worker_path = Path(__file__).with_name("molnextr_worker.py")
        self._state_lock = threading.Lock()
        self._progress = _Progress(bytes_downloaded=self._installed_bytes())
        self._prepare_thread: threading.Thread | None = None
        self._worker: _MolNexTRWorker | None = None

    def status(self) -> ExtractionEngineStatus:
        with self._state_lock:
            return self._status_unlocked()

    def prepare(self) -> ExtractionEngineStatus:
        with self._state_lock:
            if self._worker is not None and self._progress.stage == "ready":
                return self._status_unlocked()
            if self._prepare_thread is not None and self._prepare_thread.is_alive():
                return self._status_unlocked()
            self._progress = _Progress(
                stage="loading",
                message="Verifying the pinned MolNexTR checkpoint before loading it once.",
                bytes_downloaded=self._installed_bytes(),
            )
            self._prepare_thread = threading.Thread(
                target=self._prepare_worker,
                name="molnextr-prepare",
                daemon=True,
            )
            self._prepare_thread.start()
            return self._status_unlocked()

    def runtime(self) -> _MolNexTRWorker:
        with self._state_lock:
            worker = self._worker
            stage = self._progress.stage
        if worker is None or stage != "ready":
            raise ImageRecognitionError(
                503,
                "EXTRACTION_ENGINE_NOT_READY",
                "MolNexTR is not ready. Prepare the local engine and wait for it to load.",
                stage,
            )
        return worker

    def _prepare_worker(self) -> None:
        try:
            self._validate_installation()
            self._set_progress(
                stage="loading",
                message="Loading MolNexTR on Apple Silicon; this happens once per server session.",
                bytes_downloaded=MODEL_SIZE,
            )
            worker = _MolNexTRWorker.start(
                python_path=self.python_path,
                source_root=self.source_root,
                model_root=self.model_root,
                worker_path=self.worker_path,
            )
            with self._state_lock:
                self._worker = worker
                self._progress = _Progress(
                    stage="ready",
                    message="MolNexTR is loaded and ready for image-to-SMILES recognition.",
                    bytes_downloaded=MODEL_SIZE,
                )
        except Exception as exc:
            self._set_progress(
                stage="error",
                message="MolNexTR could not start. Check the local installation, then retry.",
                bytes_downloaded=self._installed_bytes(),
                error_code="EXTRACTION_ENGINE_PREPARATION_FAILED",
                technical_detail=f"{type(exc).__name__}: {exc}",
            )

    def _validate_installation(self) -> None:
        if not self.python_path.is_file():
            raise RuntimeError(f"isolated MolNexTR Python is missing: {self.python_path}")
        if not self.model_path.is_file():
            raise RuntimeError(f"MolNexTR checkpoint is missing: {self.model_path}")
        if self.model_path.stat().st_size != MODEL_SIZE:
            raise RuntimeError(
                f"checkpoint is incomplete ({self.model_path.stat().st_size} of {MODEL_SIZE} bytes)"
            )
        if _sha256(self.model_path) != MODEL_SHA256:
            raise RuntimeError("checkpoint SHA-256 does not match the pinned official model")

    def _status_unlocked(self) -> ExtractionEngineStatus:
        return ExtractionEngineStatus(
            stage=self._progress.stage,
            ready=self._progress.stage == "ready" and self._worker is not None,
            message=self._progress.message,
            bytes_downloaded=self._progress.bytes_downloaded,
            bytes_total=MODEL_SIZE,
            progress_percent=round(self._progress.bytes_downloaded * 100 / MODEL_SIZE, 1),
            model_version=MODEL_VERSION,
            error_code=self._progress.error_code,
            technical_detail=self._progress.technical_detail,
        )

    def _installed_bytes(self) -> int:
        if not self.model_path.exists():
            return 0
        return min(self.model_path.stat().st_size, MODEL_SIZE)

    def _set_progress(
        self,
        *,
        stage: EngineStage,
        message: str,
        bytes_downloaded: int,
        error_code: str | None = None,
        technical_detail: str | None = None,
    ) -> None:
        with self._state_lock:
            self._progress = _Progress(
                stage=stage,
                message=message,
                bytes_downloaded=bytes_downloaded,
                error_code=error_code,
                technical_detail=technical_detail,
            )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


_MODEL_MANAGER = _ModelManager()


def extraction_engine_status(*, hand_drawn: bool = False) -> ExtractionEngineStatus:
    del hand_drawn
    return _MODEL_MANAGER.status()


def prepare_extraction_engine(*, hand_drawn: bool = False) -> ExtractionEngineStatus:
    del hand_drawn
    return _MODEL_MANAGER.prepare()


def _validate_image(image_bytes: bytes) -> None:
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            width, height = source.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise ImageRecognitionError(
                    413,
                    "IMAGE_DIMENSIONS_EXCEEDED",
                    "The image dimensions are too large. Use at most 25 million pixels.",
                )
            source.load()
    except ImageRecognitionError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageRecognitionError(
            422,
            "INVALID_IMAGE",
            "The uploaded file is not a readable PNG, JPEG, or WebP image.",
            type(exc).__name__,
        ) from exc


def _candidate_from_prediction(prediction: dict[str, Any]) -> str:
    candidate = str(prediction.get("predicted_smiles") or "").strip()
    if not candidate:
        raise ImageRecognitionError(
            422,
            "NO_STRUCTURE_RECOGNIZED",
            "MolNexTR did not recognize a molecular structure in this image.",
        )
    return candidate


def recognize_image(
    image_bytes: bytes,
    *,
    filename: str,
    media_type: str,
    hand_drawn: bool = False,
) -> ImageExtractionResponse:
    del hand_drawn
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise ImageRecognitionError(
            415,
            "UNSUPPORTED_IMAGE_TYPE",
            "Photo recognition accepts PNG, JPEG, or WebP images only.",
        )
    if not image_bytes:
        raise ImageRecognitionError(422, "EMPTY_IMAGE", "The uploaded image is empty.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ImageRecognitionError(413, "IMAGE_TOO_LARGE", "The uploaded image exceeds 5 MB.")
    _validate_image(image_bytes)

    suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[media_type]
    try:
        with TemporaryDirectory(prefix="provenancelab-ocr-") as temporary_directory:
            image_path = Path(temporary_directory) / f"source{suffix}"
            image_path.write_bytes(image_bytes)
            prediction = _MODEL_MANAGER.runtime().predict(image_path)
    except ImageRecognitionError:
        raise
    except Exception as exc:
        raise ImageRecognitionError(
            502,
            "EXTRACTION_FAILED",
            "MolNexTR could not produce a candidate. Try a tighter, higher-contrast crop.",
            f"{type(exc).__name__}: {exc}",
        ) from exc

    candidate = _candidate_from_prediction(prediction)
    device = str(prediction.get("device_info") or "") or None
    return ImageExtractionResponse(
        candidate_smiles=candidate,
        model_version=MODEL_VERSION,
        device=device,
        source_sha256=hashlib.sha256(image_bytes).hexdigest(),
        filename=Path(filename).name or "uploaded-image",
        media_type=media_type,
        warnings=[
            "MolNexTR output is untrusted; verify every atom and bond against the source.",
            "Recognition confidence is not calibrated, so no confidence value is invented.",
        ],
    )
