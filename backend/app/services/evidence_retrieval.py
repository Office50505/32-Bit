import json
import math
import re
from dataclasses import dataclass
from typing import Any

from app.evidence.store import EvidenceStore
from app.models.evidence_assistant import (
    AtomicStatement,
    EvidenceBasis,
    EvidenceDirectness,
    EvidenceItem,
    EvidencePacket,
    EvidenceSourceType,
    EvidenceStance,
    ResolutionStatus,
    RetractionStatus,
)
from app.services.assay_evidence import StructuredAssayPacketBuilder
from app.services.claim_routing import ClaimRoute, ResolvedStatement

_PROPERTY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("molecular_formula", re.compile(r"\bmolecular formula\b", re.IGNORECASE)),
    ("molecular_weight", re.compile(r"\bmolecular (?:weight|mass)\b", re.IGNORECASE)),
    ("exact_mass", re.compile(r"\bexact mass\b", re.IGNORECASE)),
    ("logp", re.compile(r"\blog\s*p\b", re.IGNORECASE)),
    ("tpsa", re.compile(r"\btpsa\b|\btopological polar surface area\b", re.IGNORECASE)),
    ("hbd", re.compile(r"\bhydrogen bond donors?\b|\bhbd\b", re.IGNORECASE)),
    ("hba", re.compile(r"\bhydrogen bond acceptors?\b|\bhba\b", re.IGNORECASE)),
    ("rotatable_bonds", re.compile(r"\brotatable bonds?\b", re.IGNORECASE)),
)
_NUMERIC_VALUE = re.compile(
    r"(?:is|of|=|approximately|about|around)\s*"
    r"(?P<value>-?[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_FORMULA_VALUE = re.compile(
    r"\bmolecular formula\b(?:\s+of\s+[^,.]+?)?\s*(?:is|=)\s*"
    r"(?P<value>[A-Z][A-Za-z0-9]*)\b"
)
_FTS_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
_FTS_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "that",
    "the",
    "this",
    "to",
    "with",
}


@dataclass(frozen=True, slots=True)
class PropertyClaim:
    property_key: str | None
    asserted_value: str | float | None


def infer_property_claim(statement: AtomicStatement) -> PropertyClaim:
    property_key = next(
        (key for key, pattern in _PROPERTY_PATTERNS if pattern.search(statement.text)),
        None,
    )
    if property_key == "molecular_formula":
        match = _FORMULA_VALUE.search(statement.text)
        return PropertyClaim(property_key, match.group("value") if match else None)
    match = _NUMERIC_VALUE.search(statement.text)
    return PropertyClaim(
        property_key,
        float(match.group("value")) if match else None,
    )


def _property_stance(asserted: str | float | None, observed: Any) -> EvidenceStance:
    if asserted is None:
        return EvidenceStance.NEUTRAL
    if isinstance(asserted, float) and isinstance(observed, int | float):
        agrees = math.isclose(asserted, float(observed), rel_tol=0.01, abs_tol=1e-6)
    elif isinstance(asserted, str) and isinstance(observed, str):
        agrees = asserted.casefold().strip() == observed.casefold().strip()
    else:
        return EvidenceStance.NEUTRAL
    return EvidenceStance.SUPPORTS if agrees else EvidenceStance.CONTRADICTS


def _as_retraction_status(value: str) -> RetractionStatus:
    try:
        return RetractionStatus(value)
    except ValueError:
        return RetractionStatus.UNKNOWN


def build_fts_query(statement: AtomicStatement) -> str:
    prioritized = [*statement.molecule_mentions, *statement.target_mentions]
    tokens: list[str] = []
    for text in [*prioritized, statement.text]:
        for token in _FTS_TOKEN.findall(text):
            normalized = token.casefold()
            if normalized in _FTS_STOP_WORDS or len(normalized) < 2:
                continue
            if normalized not in tokens:
                tokens.append(normalized)
    if not tokens:
        raise ValueError("cannot construct a safe passage query from the statement")
    return " OR ".join(f'"{token}"' for token in tokens[:12])


class LiteraturePacketBuilder:
    """Retrieve passages conservatively as context, never as automatic entailment."""

    def __init__(
        self,
        store: EvidenceStore,
        snapshot_ids: tuple[str, ...],
        *,
        result_limit: int = 10,
    ) -> None:
        if not snapshot_ids:
            raise ValueError("literature builder requires at least one snapshot")
        if not 1 <= result_limit <= 50:
            raise ValueError("literature result limit must be between 1 and 50")
        self._store = store
        self._snapshot_ids = snapshot_ids
        self._result_limit = result_limit

    def build(self, resolved: ResolvedStatement) -> EvidencePacket:
        canonical_statement = resolved.statement.model_copy(
            update={"claim_type": resolved.routing.effective_claim_type}
        )
        if resolved.routing.route != ClaimRoute.PAPER_PASSAGE:
            return EvidencePacket(statement=canonical_statement, resolution=resolved.resolution)

        query = build_fts_query(canonical_statement)
        evidence: list[EvidenceItem] = []
        remaining = self._result_limit
        for snapshot_id in self._snapshot_ids:
            if remaining == 0:
                break
            hits = self._store.search_passages(
                snapshot_id=snapshot_id,
                query=query,
                limit=remaining,
            )
            for hit in hits:
                locator_parts = [hit.section_name]
                if hit.paragraph_number is not None:
                    locator_parts.append(f"paragraph {hit.paragraph_number}")
                if hit.sentence_start is not None and hit.sentence_end is not None:
                    locator_parts.append(
                        f"characters {hit.sentence_start}-{hit.sentence_end}"
                    )
                retraction_status = _as_retraction_status(hit.retraction_status)
                flags = ["PASSAGE_ENTAILMENT_NOT_YET_VERIFIED"]
                if retraction_status == RetractionStatus.RETRACTED:
                    flags.append("RETRACTED_PAPER_EXCLUDED")
                evidence.append(
                    EvidenceItem(
                        evidence_id=f"{snapshot_id}:PASSAGE:{hit.passage_id}",
                        source_type=EvidenceSourceType.PAPER_PASSAGE,
                        source_record_id=hit.passage_id,
                        basis=EvidenceBasis.LITERATURE_CONTEXT,
                        stance=EvidenceStance.NEUTRAL,
                        directness=EvidenceDirectness.CONTEXT_ONLY,
                        molecule_inchikey=resolved.resolution.molecule_inchikey,
                        target_id=resolved.resolution.target_id,
                        organism=resolved.resolution.organism,
                        paper_id=hit.paper_id,
                        passage_locator=", ".join(locator_parts),
                        passage_text=hit.passage_text,
                        retraction_status=retraction_status,
                        snapshot_id=snapshot_id,
                        raw_record_sha256=hit.passage_sha256,
                        quality_flags=flags,
                    )
                )
            remaining = self._result_limit - len(evidence)
        return EvidencePacket(
            statement=canonical_statement,
            resolution=resolved.resolution,
            evidence_items=evidence,
        )


class RunRecordPacketBuilder:
    def __init__(
        self,
        store: EvidenceStore,
        snapshot_ids: tuple[str, ...],
        *,
        result_limit: int = 20,
    ) -> None:
        if not snapshot_ids:
            raise ValueError("run-record builder requires at least one snapshot")
        if not 1 <= result_limit <= 50:
            raise ValueError("run-record result limit must be between 1 and 50")
        self._store = store
        self._snapshot_ids = snapshot_ids
        self._result_limit = result_limit

    def build(
        self,
        resolved: ResolvedStatement,
        *,
        record_ids: tuple[str, ...] = (),
    ) -> EvidencePacket:
        canonical_statement = resolved.statement.model_copy(
            update={"claim_type": resolved.routing.effective_claim_type}
        )
        resolution = resolved.resolution
        if (
            resolved.routing.route != ClaimRoute.RUN_RECORD
            or resolution.status != ResolutionStatus.RESOLVED
            or resolution.molecule_inchikey is None
        ):
            return EvidencePacket(statement=canonical_statement, resolution=resolution)

        claim = infer_property_claim(canonical_statement)
        evidence: list[EvidenceItem] = []
        remaining = self._result_limit
        for snapshot_id in self._snapshot_ids:
            if remaining == 0:
                break
            rows = self._store.run_record_search(
                snapshot_id=snapshot_id,
                molecule_inchikey=resolution.molecule_inchikey,
                property_key=claim.property_key,
                record_ids=record_ids,
                limit=remaining,
            )
            for row in rows:
                observed = json.loads(row["value_json"])
                numeric_value = (
                    float(observed) if isinstance(observed, int | float) else None
                )
                evidence.append(
                    EvidenceItem(
                        evidence_id=f"{snapshot_id}:RUN:{row['record_id']}",
                        source_type=EvidenceSourceType.RUN_RECORD,
                        source_record_id=row["record_id"],
                        basis=EvidenceBasis.COMPUTED,
                        stance=_property_stance(claim.asserted_value, observed),
                        directness=EvidenceDirectness.DIRECT,
                        molecule_inchikey=row["molecule_inchikey"],
                        endpoint=row["property_key"],
                        value=numeric_value,
                        unit=row["unit"],
                        assay_conditions={
                            "analysis_id": row["analysis_id"],
                            "computed_value": observed,
                            "manifest": json.loads(row["manifest_json"]),
                        },
                        retraction_status=RetractionStatus.CLEAR,
                        snapshot_id=snapshot_id,
                        raw_record_sha256=row["raw_record_sha256"],
                    )
                )
            remaining = self._result_limit - len(evidence)
        return EvidencePacket(
            statement=canonical_statement,
            resolution=resolution,
            evidence_items=evidence,
        )


class EvidencePacketBuilder:
    def __init__(
        self,
        store: EvidenceStore,
        snapshot_ids: tuple[str, ...],
    ) -> None:
        self._assays = StructuredAssayPacketBuilder(store, snapshot_ids)
        self._literature = LiteraturePacketBuilder(store, snapshot_ids)
        self._runs = RunRecordPacketBuilder(store, snapshot_ids)

    def build(
        self,
        resolved: ResolvedStatement,
        *,
        run_record_ids: tuple[str, ...] = (),
    ) -> EvidencePacket:
        if resolved.routing.route == ClaimRoute.STRUCTURED_ASSAY:
            return self._assays.build(resolved)
        if resolved.routing.route == ClaimRoute.PAPER_PASSAGE:
            return self._literature.build(resolved)
        if resolved.routing.route == ClaimRoute.RUN_RECORD:
            return self._runs.build(resolved, record_ids=run_record_ids)
        canonical_statement = resolved.statement.model_copy(
            update={"claim_type": resolved.routing.effective_claim_type}
        )
        return EvidencePacket(statement=canonical_statement, resolution=resolved.resolution)
