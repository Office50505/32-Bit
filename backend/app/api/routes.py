from fastapi import APIRouter
from rdkit import rdBase

from app.core.provenance import PIPELINE_VERSION, RULESET_VERSION
from app.models.analysis import (
    AnalyzeRequest,
    AnalyzeResponse,
    BatchAnalyzeRequest,
    BatchAnalyzeResponse,
    HealthResponse,
)
from app.services.chemistry import analyze_structure

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
