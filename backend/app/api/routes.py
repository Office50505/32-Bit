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
    Conformer3D,
    ConformerRequest,
    DocumentExtractionResponse,
    ExtractionEngineStatus,
    HealthResponse,
    ImageExtractionResponse,
    ReplayVerification,
    RunResponse,
)
from app.models.evidence_assistant import ClaimCheckRequest, ClaimCheckResponse
from app.services.chemistry import analyze_structure
from app.services.claim_runs import (
    ClaimRunIntegrityError,
    get_claim_check_run,
    persist_claim_check_run,
)
from app.services.conformers import generate_conformer
from app.services.document_extraction import MAX_PDF_BYTES, extract_pdf_candidates
from app.services.evidence_runtime import EvidenceRuntimeError, get_evidence_runtime
from app.services.identity import pairwise_identity_comparisons
from app.services.image_recognition import (
    MAX_IMAGE_BYTES,
    extraction_engine_status,
    prepare_extraction_engine,
    recognize_image,
)
from app.services.ollama import OllamaError
from app.services.report import build_run_pdf
from app.services.runs import create_run, get_run, replay_run

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
    results = [analyze_structure(item) for item in request.molecules]
    return BatchAnalyzeResponse(
        results=results,
        identity_comparisons=pairwise_identity_comparisons(results),
    )


@router.post("/conformer", response_model=Conformer3D)
def create_conformer(request: ConformerRequest) -> Conformer3D:
    return generate_conformer(request.structure)


@router.post("/evidence/check", response_model=ClaimCheckResponse)
def check_evidence_claim(request: ClaimCheckRequest) -> ClaimCheckResponse:
    try:
        response = get_evidence_runtime().check_claim(request)
        persist_claim_check_run(request, response)
        return response
    except (
        ClaimRunIntegrityError,
        EvidenceRuntimeError,
        EvidenceStoreError,
        OllamaError,
    ) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/evidence/runs/{assistant_run_id}", response_model=ClaimCheckResponse)
def read_evidence_claim_run(assistant_run_id: str) -> ClaimCheckResponse:
    response = get_claim_check_run(assistant_run_id)
    if response is None:
        raise HTTPException(status_code=404, detail="The requested claim-check run does not exist.")
    return response


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


@router.post("/extract/document", response_model=DocumentExtractionResponse)
def extract_document_candidates(
    document: Annotated[UploadFile, File()],
) -> DocumentExtractionResponse:
    payload = document.file.read(MAX_PDF_BYTES + 1)
    return extract_pdf_candidates(
        payload,
        filename=document.filename or "uploaded-paper.pdf",
        media_type=document.content_type or "application/octet-stream",
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


@router.post("/runs/{run_id}/replay", response_model=ReplayVerification)
def replay_analysis_run(run_id: str) -> ReplayVerification:
    verification = replay_run(run_id)
    if verification is None:
        raise HTTPException(status_code=404, detail="The requested run does not exist.")
    return verification


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
