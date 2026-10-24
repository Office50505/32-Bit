import sqlite3
from pathlib import Path

import pytest

from app.evidence import EvidenceStore, EvidenceStoreError, SnapshotSealedError, SnapshotSpec
from app.models.evidence_assistant import (
    EvidenceBasis,
    EvidenceDirectness,
    EvidenceItem,
    EvidenceSourceType,
    EvidenceStance,
    RetractionStatus,
)

HASH = "a" * 64
SNAPSHOT_ID = "pilot-v1"
INCHIKEY = "KTUFNOKKBVMGRW-UHFFFAOYSA-N"


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "evidence.sqlite"


@pytest.fixture
def store(database_path: Path) -> EvidenceStore:
    evidence_store = EvidenceStore.create(database_path)
    evidence_store.register_snapshot(
        SnapshotSpec(
            snapshot_id=SNAPSHOT_ID,
            source_name="ProvenanceLab pilot",
            source_version="1",
            source_sha256=HASH,
            scope={"molecules": ["imatinib"], "targets": ["ABL1"]},
            created_at="2026-10-24T00:00:00Z",
            license="mixed; see individual records",
        )
    )
    yield evidence_store
    evidence_store.close()


def seed_structured_records(store: EvidenceStore) -> None:
    store.add_molecule(
        snapshot_id=SNAPSHOT_ID,
        inchikey=INCHIKEY,
        canonical_smiles="CN1CCN(CC1)CC2=CC=C(C=C2)C(=O)NC3=CC=CC=C3",
        preferred_name="Imatinib",
        chembl_id="CHEMBL941",
        raw_record_sha256=HASH,
    )
    store.add_molecule_alias(
        snapshot_id=SNAPSHOT_ID,
        inchikey=INCHIKEY,
        alias="Imatinib",
        source="ChEMBL",
    )
    store.add_target(
        snapshot_id=SNAPSHOT_ID,
        target_id="CHEMBL1862",
        preferred_name="Tyrosine-protein kinase ABL1",
        organism="Homo sapiens",
        target_type="SINGLE PROTEIN",
        accession="P00519",
        gene_symbol="ABL1",
        raw_record_sha256=HASH,
    )
    store.add_target_alias(
        snapshot_id=SNAPSHOT_ID,
        target_id="CHEMBL1862",
        alias="ABL1",
        source="ChEMBL",
    )
    store.add_assay(
        snapshot_id=SNAPSHOT_ID,
        assay_id="CHEMBL-A1",
        source="CHEMBL",
        target_id="CHEMBL1862",
        organism="Homo sapiens",
        assay_type="B",
        description="Binding affinity against recombinant human ABL1.",
        target_confidence_score=9,
        raw_record_sha256=HASH,
    )
    store.add_activity(
        snapshot_id=SNAPSHOT_ID,
        activity_id="CHEMBL-ACT-1",
        assay_id="CHEMBL-A1",
        molecule_inchikey=INCHIKEY,
        measurement_type="IC50",
        original_value=42,
        original_unit="nM",
        original_relation="=",
        standard_value=42,
        standard_unit="nM",
        standard_relation="=",
        pchembl_value=7.38,
        raw_record_sha256=HASH,
    )


def seed_paper_and_passages(store: EvidenceStore) -> None:
    store.add_paper(
        snapshot_id=SNAPSHOT_ID,
        paper_id="PMCID:PMC1",
        pmcid="PMC1",
        pmid="1",
        doi="10.1000/example",
        title="Selective inhibition of ABL1 by imatinib",
        article_license="CC BY 4.0",
        retraction_status="CLEAR",
        raw_record_sha256=HASH,
    )
    store.add_passage(
        snapshot_id=SNAPSHOT_ID,
        passage_id="PMCID:PMC1:RESULTS:P1",
        paper_id="PMCID:PMC1",
        section_name="Results",
        paragraph_number=1,
        sentence_start=0,
        sentence_end=73,
        passage_text="Imatinib inhibited recombinant human ABL1 with nanomolar potency.",
        passage_sha256=HASH,
        priority=1,
    )
    store.add_passage(
        snapshot_id=SNAPSHOT_ID,
        passage_id="PMCID:PMC1:DISCUSSION:P4",
        paper_id="PMCID:PMC1",
        section_name="Discussion",
        paragraph_number=4,
        passage_text="These findings may inform future mechanistic experiments.",
        passage_sha256="b" * 64,
        priority=4,
    )


def test_schema_contains_all_phase2_tables(store: EvidenceStore) -> None:
    rows = store._connection.execute(  # noqa: SLF001 - verifies the storage contract
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
    ).fetchall()
    names = {row["name"] for row in rows}
    assert {
        "snapshots",
        "molecules",
        "molecule_aliases",
        "targets",
        "target_aliases",
        "target_components",
        "assays",
        "activities",
        "papers",
        "passages",
        "passages_fts",
        "retractions",
        "run_records",
        "evidence_items",
    } <= names


def test_alias_resolution_is_case_insensitive_and_explicit(store: EvidenceStore) -> None:
    seed_structured_records(store)
    molecule_matches = store.resolve_molecule_alias(SNAPSHOT_ID, "  IMATINIB ")
    target_matches = store.resolve_target_alias(SNAPSHOT_ID, "abl1")
    assert [row["inchikey"] for row in molecule_matches] == [INCHIKEY]
    assert [row["target_id"] for row in target_matches] == ["CHEMBL1862"]


def test_structured_activity_search_filters_exact_entities(store: EvidenceStore) -> None:
    seed_structured_records(store)
    rows = store.structured_activity_search(
        snapshot_id=SNAPSHOT_ID,
        molecule_inchikey=INCHIKEY,
        target_id="CHEMBL1862",
        endpoint="IC50",
        organism="Homo sapiens",
    )
    assert len(rows) == 1
    assert rows[0]["activity_id"] == "CHEMBL-ACT-1"
    assert rows[0]["standard_value"] == 42
    assert rows[0]["standard_unit"] == "nM"
    assert rows[0]["target_confidence_score"] == 9


def test_fts5_passage_search_returns_ranked_traceable_hit(store: EvidenceStore) -> None:
    seed_paper_and_passages(store)
    hits = store.search_passages(
        snapshot_id=SNAPSHOT_ID,
        query="imatinib AND ABL1",
    )
    assert [hit.passage_id for hit in hits] == [
        "PMCID:PMC1:RESULTS:P1",
        "PMCID:PMC1:DISCUSSION:P4",
    ]
    assert hits[0].section_name == "Results"
    assert hits[0].priority == 1
    assert "<mark>Imatinib</mark>" in hits[0].snippet
    assert "nanomolar potency" in hits[0].passage_text


def test_passage_and_fts_insert_are_atomic(store: EvidenceStore) -> None:
    store.add_paper(
        snapshot_id=SNAPSHOT_ID,
        paper_id="PMCID:PMC1",
        title="Example",
        retraction_status="CLEAR",
        raw_record_sha256=HASH,
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.add_passage(
            snapshot_id=SNAPSHOT_ID,
            passage_id="P1",
            paper_id="PMCID:PMC1",
            section_name="Results",
            passage_text="Example",
            passage_sha256=HASH,
            priority=9,
        )
    count = store._connection.execute(  # noqa: SLF001 - verifies transaction rollback
        "SELECT count(*) FROM passages_fts WHERE passage_id = 'P1'"
    ).fetchone()[0]
    assert count == 0


def test_evidence_item_preserves_frozen_payload(store: EvidenceStore) -> None:
    seed_structured_records(store)
    item = EvidenceItem(
        evidence_id="CHEMBL36:ACTIVITY:CHEMBL-ACT-1",
        source_type=EvidenceSourceType.CHEMBL_ACTIVITY,
        source_record_id="CHEMBL-ACT-1",
        basis=EvidenceBasis.EXPERIMENTAL,
        stance=EvidenceStance.SUPPORTS,
        directness=EvidenceDirectness.DIRECT,
        molecule_inchikey=INCHIKEY,
        target_id="CHEMBL1862",
        organism="Homo sapiens",
        endpoint="IC50",
        relation="=",
        value=42,
        unit="nM",
        retraction_status=RetractionStatus.CLEAR,
        snapshot_id=SNAPSHOT_ID,
        raw_record_sha256=HASH,
    )
    store.add_evidence_item(item)
    row = store._connection.execute(  # noqa: SLF001 - verifies serialized provenance
        "SELECT * FROM evidence_items WHERE evidence_id = ?", (item.evidence_id,)
    ).fetchone()
    assert row["source_record_id"] == "CHEMBL-ACT-1"
    assert row["basis"] == "EXPERIMENTAL"
    assert row["raw_record_sha256"] == HASH
    assert '"evidence_id":"CHEMBL36:ACTIVITY:CHEMBL-ACT-1"' in row["payload_json"]


def test_snapshot_hash_is_stable_across_identical_databases(tmp_path: Path) -> None:
    hashes: list[str] = []
    for name in ("first.sqlite", "second.sqlite"):
        with EvidenceStore.create(tmp_path / name) as evidence_store:
            evidence_store.register_snapshot(
                SnapshotSpec(
                    snapshot_id=SNAPSHOT_ID,
                    source_name="pilot",
                    source_version="1",
                    source_sha256=HASH,
                    scope={"targets": ["ABL1"]},
                    created_at="2026-10-24T00:00:00Z",
                )
            )
            seed_structured_records(evidence_store)
            hashes.append(evidence_store.seal_snapshot(SNAPSHOT_ID))
    assert hashes[0] == hashes[1]
    assert len(hashes[0]) == 64


def test_sealed_snapshot_rejects_further_writes(store: EvidenceStore) -> None:
    seed_structured_records(store)
    store.seal_snapshot(SNAPSHOT_ID)
    assert store.verify_snapshot(SNAPSHOT_ID)
    with pytest.raises(SnapshotSealedError):
        store.add_molecule_alias(
            snapshot_id=SNAPSHOT_ID,
            inchikey=INCHIKEY,
            alias="Gleevec",
            source="manual",
        )


def test_runtime_store_is_read_only_and_verifies_snapshot(
    store: EvidenceStore,
    database_path: Path,
) -> None:
    seed_structured_records(store)
    expected_hash = store.seal_snapshot(SNAPSHOT_ID)
    store.close()

    with EvidenceStore.open_read_only(database_path) as runtime_store:
        assert runtime_store.verify_snapshot(SNAPSHOT_ID)
        assert runtime_store.content_sha256(SNAPSHOT_ID) == expected_hash
        with pytest.raises(EvidenceStoreError, match="read-only"):
            runtime_store.register_snapshot(
                SnapshotSpec(
                    snapshot_id="forbidden",
                    source_name="forbidden",
                    source_version="1",
                    source_sha256=HASH,
                    scope={},
                    created_at="2026-10-24T00:00:00Z",
                )
            )


def test_foreign_keys_reject_orphan_activity(store: EvidenceStore) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        store.add_activity(
            snapshot_id=SNAPSHOT_ID,
            activity_id="ORPHAN",
            assay_id="MISSING",
            molecule_inchikey=INCHIKEY,
            measurement_type="IC50",
            raw_record_sha256=HASH,
        )


def test_missing_read_only_database_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(EvidenceStoreError, match="does not exist"):
        EvidenceStore.open_read_only(tmp_path / "missing.sqlite")


def test_ingestion_rejects_malformed_provenance_hash(store: EvidenceStore) -> None:
    with pytest.raises(EvidenceStoreError, match="SHA-256"):
        store.add_molecule(
            snapshot_id=SNAPSHOT_ID,
            inchikey=INCHIKEY,
            canonical_smiles="CCO",
            raw_record_sha256="not-a-hash",
        )
