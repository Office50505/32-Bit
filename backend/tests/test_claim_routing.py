from pathlib import Path

import pytest

from app.evidence import EvidenceStore, SnapshotSpec
from app.models.evidence_assistant import (
    AtomicStatement,
    ClaimDecomposition,
    ClaimType,
    ResolutionStatus,
)
from app.services.claim_routing import (
    ClaimRoute,
    EntityResolver,
    duplicate_statement_pairs,
    infer_endpoint,
    route_statement,
)

HASH = "a" * 64
SNAPSHOT_ID = "pilot-v1"
IMATINIB = "KTUFNOKKBVMGRW-UHFFFAOYSA-N"


@pytest.fixture
def store(tmp_path: Path) -> EvidenceStore:
    evidence_store = EvidenceStore.create(tmp_path / "evidence.sqlite")
    evidence_store.register_snapshot(
        SnapshotSpec(
            snapshot_id=SNAPSHOT_ID,
            source_name="pilot",
            source_version="1",
            source_sha256=HASH,
            scope={},
            created_at="2026-10-24T00:00:00Z",
        )
    )
    evidence_store.add_molecule(
        snapshot_id=SNAPSHOT_ID,
        inchikey=IMATINIB,
        canonical_smiles="CC",
        preferred_name="Imatinib",
        raw_record_sha256=HASH,
    )
    evidence_store.add_molecule_alias(
        snapshot_id=SNAPSHOT_ID,
        inchikey=IMATINIB,
        alias="Imatinib",
        source="pilot",
    )
    evidence_store.add_target(
        snapshot_id=SNAPSHOT_ID,
        target_id="CHEMBL1862",
        preferred_name="ABL1",
        organism="Homo sapiens",
        raw_record_sha256=HASH,
    )
    evidence_store.add_target_alias(
        snapshot_id=SNAPSHOT_ID,
        target_id="CHEMBL1862",
        alias="ABL1",
        source="pilot",
    )
    yield evidence_store
    evidence_store.close()


def make_statement(
    text: str,
    claim_type: ClaimType,
    *,
    molecules: list[str] | None = None,
    targets: list[str] | None = None,
    endpoints: list[str] | None = None,
    statement_id: str = "S1",
) -> AtomicStatement:
    return AtomicStatement(
        statement_id=statement_id,
        text=text,
        claim_type=claim_type,
        molecule_mentions=molecules or [],
        target_mentions=targets or [],
        endpoint_mentions=endpoints or [],
    )


def test_activity_signal_overrides_incorrect_model_label() -> None:
    statement = make_statement(
        "Imatinib inhibits ABL1 with nanomolar potency.",
        ClaimType.COMPUTED_PROPERTY,
        molecules=["Imatinib"],
        targets=["ABL1"],
    )
    decision = route_statement(statement)
    assert decision.effective_claim_type == ClaimType.BIOLOGICAL_ACTIVITY
    assert decision.route == ClaimRoute.STRUCTURED_ASSAY
    assert decision.model_label_overridden
    assert decision.reason_code == "DETERMINISTIC_ACTIVITY_SIGNAL"


@pytest.mark.parametrize(
    ("text", "model_type", "expected_type", "expected_route"),
    [
        (
            "The calculated LogP of imatinib is 4.5.",
            ClaimType.OTHER,
            ClaimType.COMPUTED_PROPERTY,
            ClaimRoute.RUN_RECORD,
        ),
        (
            "Imatinib will safely cure every patient with leukemia.",
            ClaimType.BIOLOGICAL_ACTIVITY,
            ClaimType.CLINICAL_OR_SAFETY,
            ClaimRoute.OUT_OF_SCOPE_REVIEW,
        ),
        (
            "Imatinib changes downstream phosphorylation pathways.",
            ClaimType.OTHER,
            ClaimType.MECHANISM,
            ClaimRoute.PAPER_PASSAGE,
        ),
    ],
)
def test_deterministic_claim_routing(
    text: str,
    model_type: ClaimType,
    expected_type: ClaimType,
    expected_route: ClaimRoute,
) -> None:
    decision = route_statement(make_statement(text, model_type))
    assert decision.effective_claim_type == expected_type
    assert decision.route == expected_route


def test_entity_resolution_uses_exact_frozen_aliases(store: EvidenceStore) -> None:
    resolver = EntityResolver(store, (SNAPSHOT_ID,))
    statement = make_statement(
        "Imatinib inhibits ABL1 with an IC50 of 42 nM.",
        ClaimType.BIOLOGICAL_ACTIVITY,
        molecules=["imatinib"],
        targets=["abl1"],
        endpoints=["IC50"],
    )
    result = resolver.resolve_and_route(statement)
    assert result.resolution.status == ResolutionStatus.RESOLVED
    assert result.resolution.molecule_inchikey == IMATINIB
    assert result.resolution.target_id == "CHEMBL1862"
    assert result.resolution.organism == "Homo sapiens"
    assert result.resolution.endpoint == "IC50"


def test_unresolved_target_never_selects_a_guess(store: EvidenceStore) -> None:
    resolver = EntityResolver(store, (SNAPSHOT_ID,))
    statement = make_statement(
        "Imatinib inhibits a mystery kinase.",
        ClaimType.BIOLOGICAL_ACTIVITY,
        molecules=["Imatinib"],
        targets=["mystery kinase"],
    )
    result = resolver.resolve_and_route(statement)
    assert result.resolution.status == ResolutionStatus.UNRESOLVED
    assert result.resolution.target_id is None
    assert result.resolution.reason_codes == ["UNRESOLVED_TARGET:mystery kinase"]


def test_ambiguous_alias_never_selects_first_match(store: EvidenceStore) -> None:
    other = "AAAAAAAAAAAAAA-BBBBBBBBBB-C"
    store.add_molecule(
        snapshot_id=SNAPSHOT_ID,
        inchikey=other,
        canonical_smiles="CCC",
        raw_record_sha256=HASH,
    )
    store.add_molecule_alias(
        snapshot_id=SNAPSHOT_ID,
        inchikey=other,
        alias="Imatinib",
        source="ambiguous-test",
    )
    resolver = EntityResolver(store, (SNAPSHOT_ID,))
    statement = make_statement(
        "Imatinib inhibits ABL1.",
        ClaimType.BIOLOGICAL_ACTIVITY,
        molecules=["Imatinib"],
        targets=["ABL1"],
    )
    result = resolver.resolve_and_route(statement)
    assert result.resolution.status == ResolutionStatus.AMBIGUOUS
    assert result.resolution.molecule_inchikey is None
    assert result.resolution.reason_codes == ["AMBIGUOUS_MOLECULE:Imatinib"]


def test_clinical_out_of_scope_does_not_require_entity_resolution(store: EvidenceStore) -> None:
    resolver = EntityResolver(store, (SNAPSHOT_ID,))
    statement = make_statement(
        "UnknownDrug will safely cure every patient.",
        ClaimType.OTHER,
        molecules=["UnknownDrug"],
    )
    result = resolver.resolve_and_route(statement)
    assert result.routing.route == ClaimRoute.OUT_OF_SCOPE_REVIEW
    assert result.resolution.status == ResolutionStatus.NOT_REQUIRED


def test_multiple_endpoints_are_explicitly_ambiguous() -> None:
    endpoint, reasons = infer_endpoint(
        make_statement(
            "The IC50 and Ki were measured.",
            ClaimType.BIOLOGICAL_ACTIVITY,
            endpoints=["IC50", "Ki"],
        )
    )
    assert endpoint is None
    assert reasons == ["MULTIPLE_ENDPOINTS_IN_STATEMENT"]


def test_duplicate_model_statements_are_detected() -> None:
    decomposition = ClaimDecomposition(
        statements=[
            make_statement(
                "Imatinib inhibits ABL1 with nanomolar potency.",
                ClaimType.BIOLOGICAL_ACTIVITY,
                molecules=["Imatinib"],
                targets=["ABL1"],
            ),
            make_statement(
                "Imatinib inhibits ABL1.",
                ClaimType.BIOLOGICAL_ACTIVITY,
                molecules=["Imatinib"],
                targets=["ABL1"],
                statement_id="S2",
            ),
        ]
    )
    assert duplicate_statement_pairs(decomposition) == [("S1", "S2")]
