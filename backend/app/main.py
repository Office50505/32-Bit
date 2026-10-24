from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.services.conformers import ConformerGenerationError
from app.services.document_extraction import DocumentExtractionError
from app.services.image_recognition import ImageRecognitionError

app = FastAPI(
    title="ProvenanceLab API",
    description="Deterministic molecular validation with explicit missing-value semantics.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(router)


@app.exception_handler(DocumentExtractionError)
async def document_extraction_error(
    _request: Request,
    exception: DocumentExtractionError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exception.status_code,
        content={
            "error": {
                "code": exception.code,
                "message": exception.message,
                "field": "document",
                "technical_detail": exception.technical_detail,
            }
        },
    )


@app.exception_handler(ConformerGenerationError)
async def conformer_generation_error(
    _request: Request,
    exception: ConformerGenerationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exception.status_code,
        content={
            "error": {
                "code": exception.code,
                "message": exception.message,
                "field": "structure",
                "technical_detail": None,
            }
        },
    )


@app.exception_handler(ImageRecognitionError)
async def image_recognition_error(
    _request: Request,
    exception: ImageRecognitionError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exception.status_code,
        content={
            "error": {
                "code": exception.code,
                "message": exception.message,
                "field": "image",
                "technical_detail": exception.technical_detail,
            }
        },
    )


def _validation_error_code(field: str, error_type: str) -> str:
    if field.endswith("structure"):
        if error_type == "string_too_short" or error_type == "value_error":
            return "EMPTY_STRUCTURE"
        if error_type == "string_too_long":
            return "STRUCTURE_TOO_LONG"
    if field.endswith("input_type") or error_type == "literal_error":
        return "UNSUPPORTED_INPUT_FORMAT"
    if field.endswith("molecules"):
        return "INVALID_BATCH_SIZE"
    if "source" in field:
        return "INVALID_SOURCE_METADATA"
    if error_type == "extra_forbidden":
        return "UNKNOWN_REQUEST_FIELD"
    return "REQUEST_VALIDATION_ERROR"


@app.exception_handler(RequestValidationError)
async def request_validation_error(
    _request: Request,
    exception: RequestValidationError,
) -> JSONResponse:
    first = exception.errors()[0]
    field = ".".join(str(part) for part in first.get("loc", ()) if part != "body") or None
    error_type = str(first.get("type", "request_validation_error"))
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": _validation_error_code(field or "", error_type),
                "message": str(first.get("msg", "The request is invalid.")),
                "field": field,
                "technical_detail": error_type,
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exception: HTTPException) -> JSONResponse:
    code = "RUN_NOT_FOUND" if exception.status_code == 404 else "HTTP_ERROR"
    return JSONResponse(
        status_code=exception.status_code,
        content={
            "error": {
                "code": code,
                "message": str(exception.detail),
                "field": None,
                "technical_detail": None,
            }
        },
    )
