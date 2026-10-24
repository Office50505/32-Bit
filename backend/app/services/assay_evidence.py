import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.evidence.store import EvidenceStore, EvidenceStoreError
from app.models.evidence_assistant import (
    AssayDisagreement,
    AssayDisagreementKind,
    AtomicStatement,
    ConflictAssessment,
    EvidenceBasis,
    EvidenceDirectness,
    EvidenceItem,
    EvidencePacket,
    EvidenceSourceType,
    EvidenceStance,
    ResolutionStatus,
    RetractionStatus,
)
from app.services.claim_routing import ClaimRoute, ResolvedStatement

EXACT_VALUE_TOLERANCE_FOLD = 3.0
NUMERIC_DISAGREEMENT_FOLD = 10.0

_UNIT_TO_MOLAR = {
    "m": 1.0,
    "mm": 1e-3,
    "um": 1e-6,
    "nm": 1e-9,
    "pm": 1e-12,
    "fm": 1e-15,
}
_VALID_RELATIONS = {"=", "<", ">", "<=", ">="}
_ACTIVE_OUTCOMES = {"active", "agonist", "antagonist", "inhibitor", "positive"}
_INACTIVE_OUTCOMES = {"inactive", "inconclusive", "negative", "not active"}
_NEGATED_ACTIVITY = re.compile(
    r"\b(?:does\s+not|doesn't|did\s+not|is\s+not|fails?\s+to)\s+"
    r"(?:inhibit|activate|bind)\b|\binactive\b",
    re.IGNORECASE,
)
_QUANTITATIVE_ACTIVITY = re.compile(
    r"(?:(?:IC|EC)\s*[-_]?\s*50|Ki|Kd|potency)"
    r"(?:\s+(?:is|of|at|below|under|above|over))?\s*"
    r"(?P<relation><=|>=|<|>|=|approximately|about|around)?\s*"
    r"(?P<value>[0-9]+(?:\.[0-9]+)?)\s*"
    r"(?P<unit>fM|pM|nM|uM|µM|μM|mM|M)\b",
    re.IGNORECASE,
)
_POTENCY_BANDS = {
    "picomolar": (1e-12, 1e-9),
    "nanomolar": (1e-9, 1e-6),
    "micromolar": (1e-6, 1e-3),
    "millimolar": (1e-3, 1.0),
}
_CONTEXT_DIMENSIONS = (
    "assay_type",
    "organism",
    "cell_line",
    "mutation",
    "protein_form",
    "substrate",
    "ph",
    "temperature",
)


@dataclass(frozen=True, slots=True)
class ActivityClaimConstraint:
    expected_active: bool
    lower_molar: float | None = None
    upper_molar: float | None = None
    exact_molar: float | None = None
    tolerance_fold: float = EXACT_VALUE_TOLERANCE_FOLD


@dataclass(frozen=True, slots=True)
class MeasurementInterval:
    lower_molar: float | None
    upper_molar: float | None
    exact_molar: float | None


def _normalized_unit(unit: str) -> str:
    return unit.strip().replace("µ", "u").replace("μ", "u").casefold()


def to_molar(value: float | None, unit: str | None) -> float | None:
    if value is None or unit is None or value < 0:
        return None
    multiplier = _UNIT_TO_MOLAR.get(_normalized_unit(unit))
    return value * multiplier if multiplier is not None else None


def measurement_interval(
    value: float | None,
    unit: str | None,
    relation: str | None,
) -> MeasurementInterval | None:
    molar = to_molar(value, unit)
    if molar is None:
        return None
    normalized_relation = relation if relation in _VALID_RELATIONS else "="
    if normalized_relation in {"<", "<="}:
        return MeasurementInterval(lower_molar=None, upper_molar=molar, exact_molar=None)
    if normalized_relation in {">", ">="}:
        return MeasurementInterval(lower_molar=molar, upper_molar=None, exact_molar=None)
    return MeasurementInterval(lower_molar=molar, upper_molar=molar, exact_molar=molar)


def parse_activity_constraint(statement: AtomicStatement) -> ActivityClaimConstraint:
    text = statement.text
    expected_active = not bool(_NEGATED_ACTIVITY.search(text))
    quantitative = _QUANTITATIVE_ACTIVITY.search(text)
    if quantitative:
        exact_molar = to_molar(
            float(quantitative.group("value")), quantitative.group("unit")
        )
        relation = (quantitative.group("relation") or "=").casefold()
        if relation in {"<", "<="}:
            return ActivityClaimConstraint(expected_active, upper_molar=exact_molar)
        if relation in {">", ">="}:
            return ActivityClaimConstraint(expected_active, lower_molar=exact_molar)
        return ActivityClaimConstraint(expected_active, exact_molar=exact_molar)

    lowered = text.casefold()
    for label, (lower, upper) in _POTENCY_BANDS.items():
        if re.search(rf"\b{label}\b", lowered):
            return ActivityClaimConstraint(
                expected_active,
                lower_molar=lower,
                upper_molar=upper,
            )
    return ActivityClaimConstraint(expected_active)


def stance_for_measurement(
    constraint: ActivityClaimConstraint,
    *,
    interval: MeasurementInterval | None,
    activity_outcome: str | None,
) -> EvidenceStance:
    outcome = activity_outcome.casefold().strip() if activity_outcome else None
    if outcome in _ACTIVE_OUTCOMES:
        outcome_active: bool | None = True
    elif outcome in _INACTIVE_OUTCOMES:
        outcome_active = False
    else:
        outcome_active = None

    if interval is not None and constraint.exact_molar is not None:
        lower = constraint.exact_molar / constraint.tolerance_fold
        upper = constraint.exact_molar * constraint.tolerance_fold
        if interval.upper_molar is not None and interval.upper_molar < lower:
            matches = False
        elif interval.lower_molar is not None and interval.lower_molar > upper:
            matches = False
        elif interval.exact_molar is not None:
            matches = lower <= interval.exact_molar <= upper
        else:
            return EvidenceStance.NEUTRAL
        return _stance_from_match(matches, constraint.expected_active)

    if interval is not None and (
        constraint.lower_molar is not None or constraint.upper_molar is not None
    ):
        below_range = (
            constraint.lower_molar is not None
            and interval.upper_molar is not None
            and interval.upper_molar < constraint.lower_molar
        )
        above_range = (
            constraint.upper_molar is not None
            and interval.lower_molar is not None
            and interval.lower_molar >= constraint.upper_molar
        )
        if below_range or above_range:
            return _stance_from_match(False, constraint.expected_active)
        entirely_inside = (
            (constraint.lower_molar is None or interval.lower_molar is not None)
            and (constraint.upper_molar is None or interval.upper_molar is not None)
            and (
                constraint.lower_molar is None
                or interval.lower_molar is not None
                and interval.lower_molar >= constraint.lower_molar
            )
            and (
                constraint.upper_molar is None
                or interval.upper_molar is not None
                and interval.upper_molar < constraint.upper_molar
            )
        )
        if entirely_inside:
            return _stance_from_match(True, constraint.expected_active)
        return EvidenceStance.NEUTRAL

    if outcome_active is not None:
        return _stance_from_match(outcome_active, constraint.expected_active)
    if interval is not None and constraint.expected_active:
        return EvidenceStance.SUPPORTS
    return EvidenceStance.NEUTRAL


def _stance_from_match(matches: bool, expected_active: bool) -> EvidenceStance:
    agrees = matches if expected_active else not matches
    return EvidenceStance.SUPPORTS if agrees else EvidenceStance.CONTRADICTS


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {"unparsed_conditions": value}
    return parsed if isinstance(parsed, dict) else {"conditions": parsed}


def _source_type(source: str) -> EvidenceSourceType:
    normalized = source.casefold()
    if normalized == "chembl":
        return EvidenceSourceType.CHEMBL_ACTIVITY
    if normalized == "pubchem":
        return EvidenceSourceType.PUBCHEM_BIOASSAY
    raise EvidenceStoreError(f"unsupported structured assay source: {source}")


def _retraction_status(value: str | None) -> RetractionStatus:
    if value is None:
        return RetractionStatus.UNKNOWN
    try:
        return RetractionStatus(value)
    except ValueError:
        return RetractionStatus.UNKNOWN


def activity_row_to_evidence(
    row: Mapping[str, Any],
    *,
    snapshot_id: str,
    constraint: ActivityClaimConstraint,
) -> EvidenceItem:
    value = row["standard_value"]
    unit = row["standard_unit"]
    relation = row["standard_relation"]
    if value is None:
        value = row["original_value"]
        unit = row["original_unit"]
        relation = row["original_relation"]
    normalized_relation = relation if relation in _VALID_RELATIONS else None
    interval = measurement_interval(value, unit, normalized_relation)
    source_type = _source_type(row["source"])
    target_confidence = row["target_confidence_score"]
    directness = EvidenceDirectness.DIRECT
    if source_type == EvidenceSourceType.CHEMBL_ACTIVITY and (
        target_confidence is None or target_confidence < 8
    ):
        directness = EvidenceDirectness.INDIRECT

    quality_flags: list[str] = []
    if row["data_validity_comment"]:
        quality_flags.append(f"DATA_VALIDITY:{row['data_validity_comment']}")
    if row["potential_duplicate"]:
        quality_flags.append("POTENTIAL_DUPLICATE")
    if target_confidence is None:
        quality_flags.append("TARGET_CONFIDENCE_NOT_REPORTED")
    elif target_confidence < 8:
        quality_flags.append("LOW_TARGET_CONFIDENCE")
    if value is not None and interval is None:
        quality_flags.append("NON_MOLAR_MEASUREMENT")

    conditions = _json_object(row["conditions_json"])
    conditions.update(
        {
            "assay_id": row["assay_id"],
            "assay_type": row["assay_type"],
            "description": row["description"],
            "target_confidence_score": target_confidence,
        }
    )
    source_label = "CHEMBL36" if source_type == EvidenceSourceType.CHEMBL_ACTIVITY else "PUBCHEM"
    return EvidenceItem(
        evidence_id=f"{snapshot_id}:{source_label}:ACTIVITY:{row['activity_id']}",
        source_type=source_type,
        source_record_id=row["activity_id"],
        basis=EvidenceBasis.EXPERIMENTAL,
        stance=stance_for_measurement(
            constraint,
            interval=interval,
            activity_outcome=row["activity_outcome"],
        ),
        directness=directness,
        molecule_inchikey=row["molecule_inchikey"],
        target_id=row["target_id"],
        organism=row["organism"],
        endpoint=row["measurement_type"],
        relation=normalized_relation,
        value=value,
        unit=unit,
        assay_conditions=conditions,
        paper_id=row["paper_id"],
        retraction_status=_retraction_status(row["paper_retraction_status"]),
        snapshot_id=snapshot_id,
        raw_record_sha256=row["activity_raw_record_sha256"],
        quality_flags=quality_flags,
    )


def _comparison_dimensions(item: EvidenceItem) -> dict[str, str]:
    dimensions: dict[str, str] = {
        "assay_type": str(item.assay_conditions.get("assay_type") or ""),
        "organism": item.organism or "",
    }
    for key in _CONTEXT_DIMENSIONS[2:]:
        value = item.assay_conditions.get(key)
        dimensions[key] = json.dumps(value, sort_keys=True) if value is not None else ""
    return dimensions


def _numeric_fold_difference(left: EvidenceItem, right: EvidenceItem) -> float | None:
    if left.relation not in {None, "="} or right.relation not in {None, "="}:
        return None
    left_molar = to_molar(left.value, left.unit)
    right_molar = to_molar(right.value, right.unit)
    if left_molar is None or right_molar is None or left_molar <= 0 or right_molar <= 0:
        return None
    return max(left_molar, right_molar) / min(left_molar, right_molar)


def assess_assay_conflicts(items: list[EvidenceItem]) -> ConflictAssessment:
    eligible = [
        item
        for item in items
        if item.basis == EvidenceBasis.EXPERIMENTAL
        and item.directness == EvidenceDirectness.DIRECT
        and item.retraction_status != RetractionStatus.RETRACTED
    ]
    disagreements: list[AssayDisagreement] = []
    for index, left in enumerate(eligible):
        for right in eligible[index + 1 :]:
            if (
                left.molecule_inchikey != right.molecule_inchikey
                or left.target_id != right.target_id
                or (left.endpoint or "").casefold() != (right.endpoint or "").casefold()
            ):
                continue
            left_dimensions = _comparison_dimensions(left)
            right_dimensions = _comparison_dimensions(right)
            differing = [
                dimension
                for dimension in _CONTEXT_DIMENSIONS
                if left_dimensions[dimension] != right_dimensions[dimension]
            ]
            comparable = not differing
            opposite_stance = {
                left.stance,
                right.stance,
            } == {EvidenceStance.SUPPORTS, EvidenceStance.CONTRADICTS}
            fold_difference = _numeric_fold_difference(left, right)
            numeric_divergence = (
                fold_difference is not None and fold_difference >= NUMERIC_DISAGREEMENT_FOLD
            )
            if not opposite_stance and not numeric_divergence:
                continue

            if opposite_stance and comparable:
                kind = AssayDisagreementKind.DIRECT_STANCE_CONFLICT
            elif opposite_stance:
                kind = AssayDisagreementKind.CONTEXTUAL_STANCE_DIFFERENCE
            else:
                kind = AssayDisagreementKind.NUMERIC_DIVERGENCE
            context = (
                "under matching typed assay context"
                if comparable
                else f"with different context ({', '.join(differing)})"
            )
            numeric = (
                f"; measurements differ by {fold_difference:.1f}-fold"
                if fold_difference is not None
                else ""
            )
            disagreements.append(
                AssayDisagreement(
                    evidence_ids=[left.evidence_id, right.evidence_id],
                    kind=kind,
                    comparable=comparable,
                    fold_difference=fold_difference,
                    differing_dimensions=differing,
                    summary=(
                        f"{left.evidence_id} and {right.evidence_id} disagree {context}{numeric}."
                    ),
                )
            )

    decision_conflict = any(
        disagreement.comparable
        and disagreement.kind == AssayDisagreementKind.DIRECT_STANCE_CONFLICT
        for disagreement in disagreements
    )
    if not disagreements:
        summary = None
    else:
        comparable_count = sum(disagreement.comparable for disagreement in disagreements)
        summary = (
            f"Found {len(disagreements)} assay disagreement(s); "
            f"{comparable_count} are directly comparable."
        )
    return ConflictAssessment(
        decision_conflict=decision_conflict,
        disagreements=disagreements,
        summary=summary,
    )


class StructuredAssayPacketBuilder:
    def __init__(
        self,
        store: EvidenceStore,
        snapshot_ids: tuple[str, ...],
        *,
        result_limit: int = 50,
    ) -> None:
        if not snapshot_ids:
            raise ValueError("packet builder requires at least one snapshot")
        if not 1 <= result_limit <= 50:
            raise ValueError("packet result limit must be between 1 and 50")
        self._store = store
        self._snapshot_ids = snapshot_ids
        self._result_limit = result_limit

    def build(self, resolved: ResolvedStatement) -> EvidencePacket:
        canonical_statement = resolved.statement.model_copy(
            update={"claim_type": resolved.routing.effective_claim_type}
        )
        resolution = resolved.resolution
        if (
            resolved.routing.route != ClaimRoute.STRUCTURED_ASSAY
            or resolution.status != ResolutionStatus.RESOLVED
            or resolution.molecule_inchikey is None
            or resolution.target_id is None
        ):
            return EvidencePacket(statement=canonical_statement, resolution=resolution)

        constraint = parse_activity_constraint(canonical_statement)
        evidence: list[EvidenceItem] = []
        remaining = self._result_limit
        for snapshot_id in self._snapshot_ids:
            if remaining == 0:
                break
            rows = self._store.structured_activity_search(
                snapshot_id=snapshot_id,
                molecule_inchikey=resolution.molecule_inchikey,
                target_id=resolution.target_id,
                endpoint=resolution.endpoint,
                organism=resolution.organism,
                limit=remaining,
            )
            evidence.extend(
                activity_row_to_evidence(
                    row,
                    snapshot_id=snapshot_id,
                    constraint=constraint,
                )
                for row in rows
            )
            remaining = self._result_limit - len(evidence)

        evidence.sort(key=_evidence_sort_key)
        return EvidencePacket(
            statement=canonical_statement,
            resolution=resolution,
            evidence_items=evidence,
            conflict_assessment=assess_assay_conflicts(evidence),
        )


def _evidence_sort_key(item: EvidenceItem) -> tuple[int, int, int, str]:
    stance_rank = {
        EvidenceStance.SUPPORTS: 0,
        EvidenceStance.CONTRADICTS: 1,
        EvidenceStance.NEUTRAL: 2,
    }[item.stance]
    directness_rank = {
        EvidenceDirectness.DIRECT: 0,
        EvidenceDirectness.INDIRECT: 1,
        EvidenceDirectness.CONTEXT_ONLY: 2,
    }[item.directness]
    quality_rank = len(item.quality_flags)
    return stance_rank, directness_rank, quality_rank, item.evidence_id


def log10_molar(item: EvidenceItem) -> float | None:
    """Expose a stable transformed value for diagnostics without hiding censoring."""

    molar = to_molar(item.value, item.unit)
    if molar is None or molar <= 0:
        return None
    return math.log10(molar)
