import json
from pathlib import Path

import pytest

from app.evidence import EvidenceStore, EvidenceStoreError
from app.evidence.pubchem import (
    PUBCHEM_CONCISE_COLUMNS,
    PubChemAssaySpec,
    PubChemMoleculeSpec,
    PubChemTargetSpec,
    import_pubchem_snapshot,
    read_pubchem_raw_files,
)
from app.evidence.retractions import FrozenRetractionIndex
from app.models.evidence_assistant import (
    AtomicStatement,
    ClaimType,
    EvidenceDirectness,
    EvidenceSourceType,
    EvidenceStance,
    RetractionStatus,
)
from app.services.claim_routing import EntityResolver
from app.services.evidence_retrieval import EvidencePacketBuilder

SNAPSHOT_ID = "pubchem-pilot-v1"
IMATINIB = "KTUFNOKKBVMGRW-UHFFFAOYSA-N"
AID = 504526


def concise_payload(*, aid: int = AID, cid: int = 5291) -> bytes:
    rows = [
        [
            str(aid),
            "104169547",
            str(cid),
            "Active",
            "P00519",
            "25",
            "4.7",
            "IC50",
            "Direct binding of imatinib to ABL1",
            "Confirmatory",
            "12345",
            "",
        ],
        [
            str(aid),
            "999999",
            "2244",
            "Inactive",
            "P00519",
            "25",
            "50",
            "IC50",
            "Direct binding of imatinib to ABL1",
            "Confirmatory",
            "12345",
            "",
        ],
    ]
    return json.dumps(
        {
            "Table": {
                "Columns": {"Column": list(PUBCHEM_CONCISE_COLUMNS)},
                "Row": [{"Cell": row} for row in rows],
            }
        },
        separators=(",", ":"),
    ).encode()


@pytest.fixture
def retraction_index(tmp_path: Path) -> FrozenRetractionIndex:
    path = tmp_path / "retractions.csv"
    path.write_text(
        "Record ID,RetractionDate,OriginalPaperDOI,OriginalPaperPubMedID,"
        "RetractionNature,Reason\n"
        "1,01/01/2020,10.1000/other,999,Retraction,Unreliable\n",
        encoding="utf-8",
    )
    return FrozenRetractionIndex.from_csv(path)


def molecule() -> PubChemMoleculeSpec:
    return PubChemMoleculeSpec(
        cid=5291,
        inchikey=IMATINIB,
        canonical_smiles="CC",
        preferred_name="Imatinib",
        aliases=("Gleevec",),
    )


def target() -> PubChemTargetSpec:
    return PubChemTargetSpec(
        target_id="CHEMBL1862",
        preferred_name="Tyrosine-protein kinase ABL1",
        organism="Homo sapiens",
        accession="P00519",
        gene_symbol="ABL1",
        aliases=("ABL",),
    )


def assay() -> PubChemAssaySpec:
    return PubChemAssaySpec(
        aid=AID,
        target_id="CHEMBL1862",
        selected_cids=(5291,),
        conditions={"cell_line": "K562"},
    )


def test_pubchem_concise_import_is_selected_normalized_and_sealed(
    tmp_path: Path,
    retraction_index: FrozenRetractionIndex,
) -> None:
    with EvidenceStore.create(tmp_path / "evidence.sqlite") as store:
        result = import_pubchem_snapshot(
            store,
            snapshot_id=SNAPSHOT_ID,
            source_version="retrieved-2026-10-24",
            created_at="2026-10-24T00:00:00Z",
            raw_files={AID: concise_payload()},
            molecules=(molecule(),),
            targets=(target(),),
            assays=(assay(),),
            retraction_index=retraction_index,
        )
        assert result.activity_count == 1
        assert result.assay_count == 1
        assert store.verify_snapshot(SNAPSHOT_ID)
        row = store._connection.execute(  # noqa: SLF001 - verifies exact normalization
            "SELECT * FROM activities"
        ).fetchone()
        assert row["activity_id"] == "PUBCHEM:AID:504526:SID:104169547:CID:5291"
        assert row["original_value"] == 4.7
        assert row["original_unit"] == "uM"
        assert row["standard_value"] == 4_700
        assert row["standard_unit"] == "nM"
        assert row["activity_outcome"] == "Active"
        assert len(row["raw_record_sha256"]) == 64
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM activities"
        ).fetchone()[0] == 1


def test_imported_pubchem_row_becomes_direct_citable_evidence(
    tmp_path: Path,
    retraction_index: FrozenRetractionIndex,
) -> None:
    database_path = tmp_path / "evidence.sqlite"
    with EvidenceStore.create(database_path) as store:
        import_pubchem_snapshot(
            store,
            snapshot_id=SNAPSHOT_ID,
            source_version="retrieved-2026-10-24",
            created_at="2026-10-24T00:00:00Z",
            raw_files={AID: concise_payload()},
            molecules=(molecule(),),
            targets=(target(),),
            assays=(assay(),),
            retraction_index=retraction_index,
        )
    with EvidenceStore.open_read_only(database_path) as store:
        statement = AtomicStatement(
            statement_id="S1",
            text="Imatinib inhibits ABL1 with micromolar potency.",
            claim_type=ClaimType.BIOLOGICAL_ACTIVITY,
            molecule_mentions=["Imatinib"],
            target_mentions=["ABL1"],
            endpoint_mentions=["IC50"],
        )
        resolved = EntityResolver(store, (SNAPSHOT_ID,)).resolve_and_route(statement)
        packet = EvidencePacketBuilder(store, (SNAPSHOT_ID,)).build(resolved)
        assert len(packet.evidence_items) == 1
        evidence = packet.evidence_items[0]
        assert evidence.source_type == EvidenceSourceType.PUBCHEM_BIOASSAY
        assert evidence.directness == EvidenceDirectness.DIRECT
        assert evidence.stance == EvidenceStance.SUPPORTS
        assert evidence.retraction_status == RetractionStatus.CLEAR
        assert evidence.assay_conditions["cell_line"] == "K562"
        assert evidence.paper_id == "PMID:12345"


def test_pubchem_import_rejects_unselected_or_mismatched_source_data(
    tmp_path: Path,
    retraction_index: FrozenRetractionIndex,
) -> None:
    with EvidenceStore.create(tmp_path / "wrong-aid.sqlite") as store:
        with pytest.raises(EvidenceStoreError, match="does not match expected"):
            import_pubchem_snapshot(
                store,
                snapshot_id=SNAPSHOT_ID,
                source_version="1",
                created_at="2026-10-24T00:00:00Z",
                raw_files={AID: concise_payload(aid=999)},
                molecules=(molecule(),),
                targets=(target(),),
                assays=(assay(),),
                retraction_index=retraction_index,
            )

    with EvidenceStore.create(tmp_path / "wrong-cid.sqlite") as store:
        with pytest.raises(EvidenceStoreError, match="no rows for selected CIDs"):
            import_pubchem_snapshot(
                store,
                snapshot_id="pubchem-pilot-v2",
                source_version="1",
                created_at="2026-10-24T00:00:00Z",
                raw_files={AID: concise_payload(cid=999)},
                molecules=(molecule(),),
                targets=(target(),),
                assays=(assay(),),
                retraction_index=retraction_index,
            )


def test_raw_file_reader_requires_exact_aid_named_files(tmp_path: Path) -> None:
    path = tmp_path / f"AID-{AID}.concise.json"
    path.write_bytes(concise_payload())
    assert read_pubchem_raw_files(tmp_path, (AID,))[AID] == concise_payload()
    with pytest.raises(EvidenceStoreError, match="missing frozen PubChem response"):
        read_pubchem_raw_files(tmp_path, (AID, 1))
