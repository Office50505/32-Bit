from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from rdkit import rdBase

from app.core.provenance import PIPELINE_VERSION, RULESET_VERSION
from app.evidence.store import EvidenceStoreError
from app.models.analysis import (
    AnalyzeRequest,
    AnalyzeResponse,
    BatchAnalyzeRequest,
    BatchAnalyzeResponse,
    ExtractionEngineStatus,
    HealthResponse,
    ImageExtractionResponse,
    RunResponse,
)
from app.models.evidence_assistant import ClaimCheckRequest, ClaimCheckResponse
from app.services.chemistry import analyze_structure
from app.services.evidence_runtime import EvidenceRuntimeError, get_evidence_runtime
from app.services.image_recognition import (
    MAX_IMAGE_BYTES,
    extraction_engine_status,
    prepare_extraction_engine,
    recognize_image,
)
from app.services.ollama import OllamaError
from app.services.report import build_run_pdf
from app.services.runs import create_run, get_run

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="provenancelab-api",
        versions={
            "pipeline": PIPELINE_VERSION,
            "ruleset": RULESET_VERSION,
            "rdkit": rdBase.rdkitVersion,
        },
    )


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return analyze_structure(request)


@router.post("/analyze/batch", response_model=BatchAnalyzeResponse)
def analyze_batch(request: BatchAnalyzeRequest) -> BatchAnalyzeResponse:
    return BatchAnalyzeResponse(results=[analyze_structure(item) for item in request.molecules])


@router.post("/evidence/check", response_model=ClaimCheckResponse)
def check_evidence_claim(request: ClaimCheckRequest) -> ClaimCheckResponse:
    try:
        return get_evidence_runtime().check_claim(request)
    except (EvidenceRuntimeError, EvidenceStoreError, OllamaError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/extract/image/engine", response_model=ExtractionEngineStatus)
def read_extraction_engine(hand_drawn: bool = False) -> ExtractionEngineStatus:
    return extraction_engine_status(hand_drawn=hand_drawn)


@router.post("/extract/image/engine/prepare", response_model=ExtractionEngineStatus)
def prepare_image_extraction_engine(hand_drawn: bool = False) -> ExtractionEngineStatus:
    return prepare_extraction_engine(hand_drawn=hand_drawn)


@router.post("/extract/image", response_model=ImageExtractionResponse)
def extract_image_candidate(
    image: Annotated[UploadFile, File()],
    hand_drawn: Annotated[bool, Form()] = False,
) -> ImageExtractionResponse:
    image_bytes = image.file.read(MAX_IMAGE_BYTES + 1)
    return recognize_image(
        image_bytes,
        filename=image.filename or "uploaded-image",
        media_type=image.content_type or "application/octet-stream",
        hand_drawn=hand_drawn,
    )


@router.post("/runs", response_model=RunResponse)
def create_analysis_run(request: BatchAnalyzeRequest) -> RunResponse:
    return create_run(request)


@router.get("/runs/{run_id}", response_model=RunResponse)
def read_analysis_run(run_id: str) -> RunResponse:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="The requested run does not exist.")
    return run


@router.get("/runs/{run_id}/report.pdf")
def download_run_report(run_id: str) -> StreamingResponse:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="The requested run does not exist.")
    pdf = build_run_pdf(run)
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{run_id}-report.pdf"',
            "Content-Length": str(len(pdf)),
            "X-ProvenanceLab-Run-ID": run_id,
        },
    )
