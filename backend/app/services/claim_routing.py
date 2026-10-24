import re
import sqlite3
from dataclasses import dataclass
from enum import StrEnum

from app.evidence.store import EvidenceStore
from app.models.evidence_assistant import (
    AtomicStatement,
    ClaimDecomposition,
    ClaimType,
    ResolutionStatus,
    ResolutionSummary,
)


class ClaimRoute(StrEnum):
    STRUCTURED_ASSAY = "STRUCTURED_ASSAY"
    PAPER_PASSAGE = "PAPER_PASSAGE"
    RUN_RECORD = "RUN_RECORD"
    OUT_OF_SCOPE_REVIEW = "OUT_OF_SCOPE_REVIEW"


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    effective_claim_type: ClaimType
    route: ClaimRoute
    model_claim_type: ClaimType
    reason_code: str

    @property
    def model_label_overridden(self) -> bool:
        return self.effective_claim_type != self.model_claim_type


@dataclass(frozen=True, slots=True)
class ResolvedStatement:
    statement: AtomicStatement
    routing: RoutingDecision
    resolution: ResolutionSummary


_CLINICAL_PATTERNS = (
    r"\bwill\s+(?:safely\s+)?cure\b",
    r"\bclinical(?:ly)?\s+(?:safe|effective|efficacy)\b",
    r"\bsafe\s+(?:for|in)\s+(?:patients?|humans?)\b",
    r"\bpatient[- ]specific\b",
    r"\bpersonalized\s+treatment\b",
    r"\bshould\s+(?:i|the patient)\s+(?:take|use)\b",
    r"\bno\s+(?:side effects?|toxicity)\b",
)
_ACTIVITY_PATTERNS = (
    r"\binhibit(?:s|ed|ion)?\b",
    r"\bactivat(?:e|es|ed|ion)\b",
    r"\bagonist\b",
    r"\bantagonist\b",
    r"\bbind(?:s|ing|ing affinity)?\b",
    r"\bpoten(?:cy|t)\b",
    r"\b(?:ic|ec)\s*50\b",
    r"\bki\b",
    r"\bkd\b",
)
_COMPUTED_PATTERNS = (
    r"\bcalculated\b",
    r"\bcomputed\b",
    r"\bmolecular (?:weight|formula|mass)\b",
    r"\bexact mass\b",
    r"\blog\s*p\b",
    r"\btpsa\b",
    r"\bhydrogen bond (?:donors?|acceptors?)\b",
    r"\brotatable bonds?\b",
)
_MECHANISM_PATTERNS = (
    r"\bmechanism\b",
    r"\bpathway\b",
    r"\bphosphorylat(?:e|es|ed|ion)\b",
    r"\bupregulat(?:e|es|ed|ion)\b",
    r"\bdownregulat(?:e|es|ed|ion)\b",
)

_ENDPOINT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("IC50", re.compile(r"\bic\s*[-_]?\s*50\b", re.IGNORECASE)),
    ("EC50", re.compile(r"\bec\s*[-_]?\s*50\b", re.IGNORECASE)),
    ("Ki", re.compile(r"\bki\b", re.IGNORECASE)),
    ("Kd", re.compile(r"\bkd\b", re.IGNORECASE)),
)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def route_statement(statement: AtomicStatement) -> RoutingDecision:
    text = statement.text
    if _matches_any(text, _CLINICAL_PATTERNS):
        effective_type = ClaimType.CLINICAL_OR_SAFETY
        route = ClaimRoute.OUT_OF_SCOPE_REVIEW
        reason = "DETERMINISTIC_CLINICAL_OR_SAFETY_SIGNAL"
    elif _matches_any(text, _ACTIVITY_PATTERNS):
        effective_type = ClaimType.BIOLOGICAL_ACTIVITY
        route = ClaimRoute.STRUCTURED_ASSAY
        reason = "DETERMINISTIC_ACTIVITY_SIGNAL"
    elif _matches_any(text, _COMPUTED_PATTERNS):
        effective_type = ClaimType.COMPUTED_PROPERTY
        route = ClaimRoute.RUN_RECORD
        reason = "DETERMINISTIC_COMPUTED_PROPERTY_SIGNAL"
    elif _matches_any(text, _MECHANISM_PATTERNS):
        effective_type = ClaimType.MECHANISM
        route = ClaimRoute.PAPER_PASSAGE
        reason = "DETERMINISTIC_MECHANISM_SIGNAL"
    else:
        effective_type = statement.claim_type
        route = {
            ClaimType.BIOLOGICAL_ACTIVITY: ClaimRoute.STRUCTURED_ASSAY,
            ClaimType.COMPUTED_PROPERTY: ClaimRoute.RUN_RECORD,
            ClaimType.CLINICAL_OR_SAFETY: ClaimRoute.OUT_OF_SCOPE_REVIEW,
            ClaimType.MECHANISM: ClaimRoute.PAPER_PASSAGE,
            ClaimType.LITERATURE_FACT: ClaimRoute.PAPER_PASSAGE,
            ClaimType.OTHER: ClaimRoute.PAPER_PASSAGE,
        }[effective_type]
        reason = "MODEL_LABEL_WITH_NO_DETERMINISTIC_OVERRIDE"
    return RoutingDecision(
        effective_claim_type=effective_type,
        route=route,
        model_claim_type=statement.claim_type,
        reason_code=reason,
    )


def infer_endpoint(statement: AtomicStatement) -> tuple[str | None, list[str]]:
    combined = " ".join([statement.text, *statement.endpoint_mentions])
    matches = [endpoint for endpoint, pattern in _ENDPOINT_PATTERNS if pattern.search(combined)]
    unique = list(dict.fromkeys(matches))
    if len(unique) == 1:
        return unique[0], []
    if len(unique) > 1:
        return None, ["MULTIPLE_ENDPOINTS_IN_STATEMENT"]
    return None, []


class EntityResolver:
    def __init__(self, store: EvidenceStore, snapshot_ids: tuple[str, ...]) -> None:
        if not snapshot_ids:
            raise ValueError("entity resolver requires at least one snapshot")
        self._store = store
        self._snapshot_ids = snapshot_ids

    def resolve(self, statement: AtomicStatement, routing: RoutingDecision) -> ResolutionSummary:
        if routing.route == ClaimRoute.OUT_OF_SCOPE_REVIEW:
            return ResolutionSummary(status=ResolutionStatus.NOT_REQUIRED)

        molecule_ids, molecule_reasons = self._resolve_molecules(statement.molecule_mentions)
        target_ids, target_rows, target_reasons = self._resolve_targets(statement.target_mentions)
        endpoint, endpoint_reasons = infer_endpoint(statement)
        reasons = [*molecule_reasons, *target_reasons, *endpoint_reasons]

        molecule_required = routing.effective_claim_type in {
            ClaimType.BIOLOGICAL_ACTIVITY,
            ClaimType.MECHANISM,
            ClaimType.COMPUTED_PROPERTY,
        }
        target_required = routing.effective_claim_type in {
            ClaimType.BIOLOGICAL_ACTIVITY,
            ClaimType.MECHANISM,
        }
        if molecule_required and not statement.molecule_mentions:
            reasons.append("MISSING_MOLECULE_MENTION")
        if target_required and not statement.target_mentions:
            reasons.append("MISSING_TARGET_MENTION")

        ambiguous_reasons = [reason for reason in reasons if reason.startswith("AMBIGUOUS_")]
        ambiguous_reasons.extend(
            reason
            for reason in reasons
            if reason in {"MULTIPLE_MOLECULES_IN_STATEMENT", "MULTIPLE_TARGETS_IN_STATEMENT"}
        )
        if ambiguous_reasons or endpoint_reasons:
            status = ResolutionStatus.AMBIGUOUS
        elif reasons:
            status = ResolutionStatus.UNRESOLVED
        elif not molecule_ids and not target_ids:
            status = ResolutionStatus.NOT_REQUIRED
        else:
            status = ResolutionStatus.RESOLVED

        organism_values = {
            row["organism"] for row in target_rows.values() if row["organism"] is not None
        }
        organism = next(iter(organism_values)) if len(organism_values) == 1 else None
        return ResolutionSummary(
            status=status,
            molecule_inchikey=next(iter(molecule_ids)) if len(molecule_ids) == 1 else None,
            target_id=next(iter(target_ids)) if len(target_ids) == 1 else None,
            organism=organism,
            endpoint=endpoint,
            reason_codes=list(dict.fromkeys(reasons)),
        )

    def resolve_and_route(self, statement: AtomicStatement) -> ResolvedStatement:
        routing = route_statement(statement)
        return ResolvedStatement(
            statement=statement,
            routing=routing,
            resolution=self.resolve(statement, routing),
        )

    def _resolve_molecules(self, mentions: list[str]) -> tuple[set[str], list[str]]:
        resolved: set[str] = set()
        reasons: list[str] = []
        for mention in mentions:
            matches: dict[str, sqlite3.Row] = {}
            for snapshot_id in self._snapshot_ids:
                for row in self._store.resolve_molecule_alias(snapshot_id, mention):
                    matches[row["inchikey"]] = row
            if not matches:
                reasons.append(f"UNRESOLVED_MOLECULE:{mention}")
            elif len(matches) > 1:
                reasons.append(f"AMBIGUOUS_MOLECULE:{mention}")
            else:
                resolved.update(matches)
        if len(resolved) > 1:
            reasons.append("MULTIPLE_MOLECULES_IN_STATEMENT")
        return resolved, reasons

    def _resolve_targets(
        self,
        mentions: list[str],
    ) -> tuple[set[str], dict[str, sqlite3.Row], list[str]]:
        resolved: set[str] = set()
        resolved_rows: dict[str, sqlite3.Row] = {}
        reasons: list[str] = []
        for mention in mentions:
            matches: dict[str, sqlite3.Row] = {}
            for snapshot_id in self._snapshot_ids:
                for row in self._store.resolve_target_alias(snapshot_id, mention):
                    matches[row["target_id"]] = row
            if not matches:
                reasons.append(f"UNRESOLVED_TARGET:{mention}")
            elif len(matches) > 1:
                reasons.append(f"AMBIGUOUS_TARGET:{mention}")
            else:
                resolved.update(matches)
                resolved_rows.update(matches)
        if len(resolved) > 1:
            reasons.append("MULTIPLE_TARGETS_IN_STATEMENT")
        return resolved, resolved_rows, reasons


def duplicate_statement_pairs(decomposition: ClaimDecomposition) -> list[tuple[str, str]]:
    duplicates: list[tuple[str, str]] = []
    statements = decomposition.statements
    for index, left in enumerate(statements):
        left_tokens = _normalized_tokens(left.text)
        for right in statements[index + 1 :]:
            right_tokens = _normalized_tokens(right.text)
            if not left_tokens or not right_tokens:
                continue
            mention_match = (
                {value.casefold() for value in left.molecule_mentions}
                == {value.casefold() for value in right.molecule_mentions}
                and {value.casefold() for value in left.target_mentions}
                == {value.casefold() for value in right.target_mentions}
            )
            overlap = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
            if mention_match and overlap >= 0.8:
                duplicates.append((left.statement_id, right.statement_id))
    return duplicates


def _normalized_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.casefold()))
