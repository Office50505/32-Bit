from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from rdkit import Chem, rdBase

from app.models.analysis import (
    DocumentExtractionResponse,
    DocumentMention,
    DocumentMoleculeCandidate,
)

MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 300
MAX_DOCUMENT_CANDIDATES = 100

TAGGED_SMILES = re.compile(
    r"\b(?:(?:canonical|isomeric)\s+)?SMILES(?:\s+string)?\s*[:=]\s*([^\s,;]{1,500})",
    re.IGNORECASE,
)
STRUCTURE_TOKEN = re.compile(
    r"(?<![\w])([A-Za-z0-9@+\-\[\]()=#$\\/.%]{3,500})(?![\w])"
)
COMPOUND_LABEL = re.compile(
    r"\b(?:compound|molecule|ligand|analogue|analog)\s+([A-Za-z0-9][A-Za-z0-9-]{0,30})",
    re.IGNORECASE,
)
SMILES_SIGNAL = re.compile(r"[\[\]()=#@\\/]|[A-Za-z]\d")


class DocumentExtractionError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        technical_detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.technical_detail = technical_detail


@dataclass
class _CandidateRecord:
    smiles: str
    canonical_smiles: str | None
    confidence: str
    label: str | None = None
    mentions: list[DocumentMention] = field(default_factory=list)


def _clean_token(value: str) -> str:
    return value.strip().strip('"\'“”‘’').rstrip(".,;:")


def _canonicalize(value: str) -> str | None:
    with rdBase.BlockLogs():
        molecule = Chem.MolFromSmiles(value)
    if molecule is None or molecule.GetNumAtoms() < 2:
        return None
    return Chem.MolToSmiles(molecule, isomericSmiles=True)


def _excerpt(text: str, start: int, end: int) -> str:
    left = max(0, start - 120)
    right = min(len(text), end + 160)
    return re.sub(r"\s+", " ", text[left:right]).strip()[:600]


def _label_before(text: str, start: int) -> str | None:
    context = text[max(0, start - 140) : start]
    labels = list(COMPOUND_LABEL.finditer(context))
    if not labels:
        return None
    return f"Compound {labels[-1].group(1)}"


def _add_candidate(
    records: OrderedDict[str, _CandidateRecord],
    *,
    token: str,
    page: int,
    text: str,
    start: int,
    end: int,
    method: str,
) -> None:
    smiles = _clean_token(token)
    if not smiles:
        return
    canonical = _canonicalize(smiles)
    if canonical is None and method != "tagged-smiles":
        return
    key = canonical or f"unresolved:{smiles}"
    label = _label_before(text, start)
    confidence = "high" if method == "tagged-smiles" and canonical else (
        "needs-review" if canonical is None else "medium"
    )
    record = records.get(key)
    if record is None:
        record = _CandidateRecord(
            smiles=smiles,
            canonical_smiles=canonical,
            confidence=confidence,
            label=label,
        )
        records[key] = record
    elif record.label is None and label is not None:
        record.label = label
    locator_kind = "SMILES field" if method == "tagged-smiles" else "structure token"
    mention = DocumentMention(
        page=page,
        excerpt=_excerpt(text, start, end),
        label=label,
        locator=f"Page {page} · {locator_kind}",
        extraction_method=method,
    )
    if mention not in record.mentions:
        record.mentions.append(mention)


def extract_candidates_from_pages(pages: list[str]) -> tuple[list[DocumentMoleculeCandidate], int]:
    records: OrderedDict[str, _CandidateRecord] = OrderedDict()
    for page_number, raw_text in enumerate(pages, start=1):
        text = raw_text or ""
        tagged_spans: list[tuple[int, int]] = []
        for match in TAGGED_SMILES.finditer(text):
            token_start, token_end = match.span(1)
            tagged_spans.append((token_start, token_end))
            _add_candidate(
                records,
                token=match.group(1),
                page=page_number,
                text=text,
                start=token_start,
                end=token_end,
                method="tagged-smiles",
            )
            if len(records) >= MAX_DOCUMENT_CANDIDATES:
                break
        if len(records) >= MAX_DOCUMENT_CANDIDATES:
            break
        for match in STRUCTURE_TOKEN.finditer(text):
            if any(start <= match.start(1) < end for start, end in tagged_spans):
                continue
            token = _clean_token(match.group(1))
            if not SMILES_SIGNAL.search(token):
                continue
            _add_candidate(
                records,
                token=token,
                page=page_number,
                text=text,
                start=match.start(1),
                end=match.end(1),
                method="structure-token",
            )
            if len(records) >= MAX_DOCUMENT_CANDIDATES:
                break
        if len(records) >= MAX_DOCUMENT_CANDIDATES:
            break

    candidates: list[DocumentMoleculeCandidate] = []
    for index, record in enumerate(records.values(), start=1):
        identity = record.canonical_smiles or record.smiles
        candidates.append(
            DocumentMoleculeCandidate(
                candidate_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
                label=record.label or f"Molecule {index}",
                smiles=record.smiles,
                canonical_smiles=record.canonical_smiles,
                confidence=record.confidence,
                mentions=record.mentions,
                mention_count=len(record.mentions),
            )
        )
    return candidates, sum(item.mention_count for item in candidates)


def extract_pdf_candidates(
    payload: bytes,
    *,
    filename: str,
    media_type: str,
) -> DocumentExtractionResponse:
    if media_type != "application/pdf" and not filename.lower().endswith(".pdf"):
        raise DocumentExtractionError(
            415,
            "UNSUPPORTED_DOCUMENT_TYPE",
            "Paper extraction currently accepts PDF files only.",
        )
    if not payload:
        raise DocumentExtractionError(422, "EMPTY_DOCUMENT", "The uploaded PDF is empty.")
    if len(payload) > MAX_PDF_BYTES:
        raise DocumentExtractionError(
            413,
            "DOCUMENT_TOO_LARGE",
            "Choose a PDF smaller than 25 MB.",
        )
    try:
        reader = PdfReader(BytesIO(payload), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as error:
                raise DocumentExtractionError(
                    422,
                    "ENCRYPTED_DOCUMENT",
                    "The PDF is encrypted and cannot be inspected.",
                ) from error
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentExtractionError(
                422,
                "DOCUMENT_PAGE_LIMIT",
                f"The PDF has {len(reader.pages)} pages; the limit is {MAX_PDF_PAGES}.",
            )
        pages = [(page.extract_text() or "") for page in reader.pages]
    except DocumentExtractionError:
        raise
    except (PdfReadError, ValueError, OSError) as error:
        raise DocumentExtractionError(
            422,
            "INVALID_PDF",
            "The uploaded file is not a readable PDF.",
            type(error).__name__,
        ) from error

    candidates, total_mentions = extract_candidates_from_pages(pages)
    warnings: list[str] = []
    if not any(page.strip() for page in pages):
        warnings.append(
            "No searchable text was found. This PDF may be scanned; upload individual "
            "structure images for diagram recognition."
        )
    elif not candidates:
        warnings.append(
            "No explicit SMILES strings were found in the searchable text. Diagram-only "
            "structures still require cropped image recognition."
        )
    if len(candidates) >= MAX_DOCUMENT_CANDIDATES:
        warnings.append(
            f"Only the first {MAX_DOCUMENT_CANDIDATES} unique candidates were returned."
        )
    return DocumentExtractionResponse(
        source_sha256=hashlib.sha256(payload).hexdigest(),
        filename=filename,
        candidates=candidates,
        total_mentions=total_mentions,
        warnings=warnings,
    )
