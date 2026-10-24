import sqlite3
from pathlib import Path

import pytest

from app.evidence import EvidenceStore
from app.evidence.build_chembl36_snapshot import build_snapshot, load_selection
from app.evidence.chembl36 import (
    OFFICIAL_ARCHIVE_SHA256,
    Chembl36Extractor,
    Chembl36Selection,
    ChemblExtractionError,
    sha256_file,
)
from app.evidence.store import EvidenceStoreError

INCHIKEY = "KTUFNOKKBVMGRW-UHFFFAOYSA-N"


def create_chembl_fixture(path: Path, *, release: str = "ChEMBL_36") -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE version (name TEXT PRIMARY KEY, creation_date TEXT, comments TEXT);
        CREATE TABLE molecule_dictionary (
            molregno INTEGER PRIMARY KEY, pref_name TEXT, chembl_id TEXT NOT NULL
        );
        CREATE TABLE compound_structures (
            molregno INTEGER PRIMARY KEY, standard_inchi_key TEXT NOT NULL,
            canonical_smiles TEXT
        );
        CREATE TABLE molecule_hierarchy (
            molregno INTEGER PRIMARY KEY, parent_molregno INTEGER, active_molregno INTEGER
        );
        CREATE TABLE molecule_synonyms (
            molsyn_id INTEGER PRIMARY KEY, molregno INTEGER, syn_type TEXT, synonyms TEXT
        );
        CREATE TABLE compound_records (
            record_id INTEGER PRIMARY KEY, molregno INTEGER, doc_id INTEGER,
            compound_name TEXT
        );
        CREATE TABLE target_dictionary (
            tid INTEGER PRIMARY KEY, target_type TEXT, pref_name TEXT,
            organism TEXT, chembl_id TEXT NOT NULL
        );
        CREATE TABLE target_components (
            targcomp_id INTEGER PRIMARY KEY, tid INTEGER, component_id INTEGER,
            homologue INTEGER NOT NULL
        );
        CREATE TABLE component_sequences (
            component_id INTEGER PRIMARY KEY, accession TEXT, component_type TEXT,
            description TEXT, organism TEXT
        );
        CREATE TABLE component_synonyms (
            compsyn_id INTEGER PRIMARY KEY, component_id INTEGER,
            component_synonym TEXT, syn_type TEXT
        );
        CREATE TABLE docs (
            doc_id INTEGER PRIMARY KEY, pubmed_id INTEGER, doi TEXT,
            chembl_id TEXT NOT NULL, title TEXT, doc_type TEXT
        );
        CREATE TABLE assays (
            assay_id INTEGER PRIMARY KEY, doc_id INTEGER, description TEXT,
            assay_type TEXT, assay_test_type TEXT, assay_category TEXT,
            assay_organism TEXT, assay_strain TEXT, assay_tissue TEXT,
            assay_cell_type TEXT, assay_subcellular_fraction TEXT,
            tid INTEGER, relationship_type TEXT, confidence_score INTEGER,
            chembl_id TEXT NOT NULL, bao_format TEXT, variant_id INTEGER,
            assay_group TEXT
        );
        CREATE TABLE activities (
            activity_id INTEGER PRIMARY KEY, assay_id INTEGER, molregno INTEGER,
            type TEXT, relation TEXT, value REAL, units TEXT, text_value TEXT,
            standard_type TEXT, standard_relation TEXT, standard_value REAL,
            standard_units TEXT, standard_text_value TEXT, pchembl_value REAL,
            activity_comment TEXT, data_validity_comment TEXT,
            potential_duplicate INTEGER
        );
        """
    )
    connection.execute("INSERT INTO version VALUES (?, '2025-07-01', NULL)", (release,))
    connection.execute(
        "INSERT INTO molecule_dictionary VALUES (1, 'Imatinib', 'CHEMBL941')"
    )
    connection.execute(
        "INSERT INTO compound_structures VALUES (1, ?, ?)",
        (INCHIKEY, "Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1"),
    )
    connection.execute("INSERT INTO molecule_hierarchy VALUES (1, 1, 1)")
    connection.executemany(
        "INSERT INTO molecule_synonyms VALUES (?, 1, ?, ?)",
        [
            (1, "TRADE_NAME", "Gleevec"),
            (2, "RESEARCH_CODE", "STI-571"),
        ],
    )
    connection.execute("INSERT INTO compound_records VALUES (1, 1, 1, 'imatinib mesylate')")
    connection.execute(
        """
        INSERT INTO target_dictionary
        VALUES (10, 'SINGLE PROTEIN', 'Tyrosine-protein kinase ABL1',
                'Homo sapiens', 'CHEMBL1862')
        """
    )
    connection.execute(
        "INSERT INTO component_sequences VALUES (100, 'P00519', 'PROTEIN', ?, 'Homo sapiens')",
        ("Tyrosine-protein kinase ABL1",),
    )
    connection.execute("INSERT INTO target_components VALUES (1, 10, 100, 0)")
    connection.executemany(
        "INSERT INTO component_synonyms VALUES (?, 100, ?, ?)",
        [
            (1, "ABL1", "GENE_SYMBOL"),
            (2, "c-Abl", "UNIPROT"),
        ],
    )
    connection.execute(
        """
        INSERT INTO docs VALUES (
            20, 123456, '10.1000/example', 'CHEMBL-DOC-1',
            'Selective inhibition of ABL1', 'PUBLICATION'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO assays VALUES (
            30, 20, 'Binding affinity against recombinant ABL1',
            'B', 'in vitro', 'confirmatory', 'Homo sapiens', NULL, NULL,
            NULL, NULL, 10, 'D', 9, 'CHEMBL-ASSAY-1', 'BAO_0000357',
            NULL, 'ABL1_BINDING'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO activities VALUES (
            40, 30, 1, 'IC50', '>', 10.0, 'nM', NULL,
            'IC50', '>', 10.0, 'nM', NULL, 8.0,
            'Dose-response curve', NULL, 0
        )
        """
    )
    connection.commit()
    connection.close()


def selection() -> Chembl36Selection:
    return Chembl36Selection(
        molecule_chembl_ids=("CHEMBL941",),
        target_chembl_ids=("CHEMBL1862",),
        endpoints=("IC50",),
    )


def test_extracts_scoped_chembl36_records_with_provenance(tmp_path: Path) -> None:
    source_path = tmp_path / "chembl_36.db"
    output_path = tmp_path / "evidence.sqlite"
    create_chembl_fixture(source_path)
    extracted_hash = sha256_file(source_path)

    with EvidenceStore.create(output_path) as store:
        with Chembl36Extractor(source_path) as extractor:
            stats = extractor.extract(
                destination=store,
                snapshot_id="chembl36-pilot-v1",
                selection=selection(),
                extracted_database_sha256=extracted_hash,
                created_at="2026-10-24T00:00:00Z",
            )

        assert stats.molecules == 1
        assert stats.targets == 1
        assert stats.target_components == 1
        assert stats.papers == 1
        assert stats.assays == 1
        assert stats.activities == 1

        snapshot = store._connection.execute(  # noqa: SLF001
            "SELECT * FROM snapshots WHERE snapshot_id = 'chembl36-pilot-v1'"
        ).fetchone()
        assert snapshot["source_version"] == "36"
        assert snapshot["source_sha256"] == OFFICIAL_ARCHIVE_SHA256
        assert snapshot["extracted_sha256"] == extracted_hash
        assert snapshot["source_doi"] == "10.6019/CHEMBL.database.36"

        molecule_matches = store.resolve_molecule_alias("chembl36-pilot-v1", "gleevec")
        target_matches = store.resolve_target_alias("chembl36-pilot-v1", "abl1")
        assert molecule_matches[0]["inchikey"] == INCHIKEY
        assert target_matches[0]["target_id"] == "CHEMBL1862"

        component = store._connection.execute(  # noqa: SLF001
            "SELECT * FROM target_components"
        ).fetchone()
        assert component["accession"] == "P00519"
        assert component["homologue"] == 0

        activities = store.structured_activity_search(
            snapshot_id="chembl36-pilot-v1",
            molecule_inchikey=INCHIKEY,
            target_id="CHEMBL1862",
            endpoint="IC50",
            organism="Homo sapiens",
        )
        assert len(activities) == 1
        assert activities[0]["standard_relation"] == ">"
        assert activities[0]["standard_value"] == 10
        assert activities[0]["paper_id"] == "CHEMBL-DOC-1"

        store.seal_snapshot("chembl36-pilot-v1")
        assert store.verify_snapshot("chembl36-pilot-v1")


def test_rejects_wrong_numbered_release(tmp_path: Path) -> None:
    source_path = tmp_path / "chembl_37.db"
    create_chembl_fixture(source_path, release="ChEMBL_37")
    with pytest.raises(ChemblExtractionError, match="expected ChEMBL_36"):
        Chembl36Extractor(source_path)


def test_rejects_missing_selected_entity_before_creating_snapshot(tmp_path: Path) -> None:
    source_path = tmp_path / "chembl_36.db"
    output_path = tmp_path / "evidence.sqlite"
    create_chembl_fixture(source_path)
    missing = Chembl36Selection(
        molecule_chembl_ids=("CHEMBL999999",),
        target_chembl_ids=("CHEMBL1862",),
    )
    with EvidenceStore.create(output_path) as store:
        with Chembl36Extractor(source_path) as extractor:
            with pytest.raises(ChemblExtractionError, match="absent from ChEMBL 36"):
                extractor.extract(
                    destination=store,
                    snapshot_id="must-not-exist",
                    selection=missing,
                    extracted_database_sha256=sha256_file(source_path),
                    created_at="2026-10-24T00:00:00Z",
                )
        count = store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM snapshots"
        ).fetchone()[0]
        assert count == 0


@pytest.mark.parametrize(
    "identifier",
    ["", "941", "CHEMBL", "CHEMBLABC", "PUBCHEM941"],
)
def test_selection_rejects_invalid_chembl_identifier(identifier: str) -> None:
    with pytest.raises(ValueError, match="invalid ChEMBL identifier"):
        Chembl36Selection(
            molecule_chembl_ids=(identifier,),
            target_chembl_ids=("CHEMBL1862",),
        )


def test_file_hash_is_content_sensitive(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"release-36")
    first = sha256_file(source)
    source.write_bytes(b"release-37")
    second = sha256_file(source)
    assert len(first) == 64
    assert first != second


def test_atomic_builder_creates_verified_read_only_snapshot(tmp_path: Path) -> None:
    source_path = tmp_path / "chembl_36.db"
    output_path = tmp_path / "evidence.sqlite"
    create_chembl_fixture(source_path)
    stats, content_hash, extracted_hash = build_snapshot(
        source_database=source_path,
        output_database=output_path,
        selection=selection(),
        snapshot_id="chembl36-pilot-v1",
        created_at="2026-10-24T00:00:00Z",
    )
    assert stats.activities == 1
    assert len(content_hash) == 64
    assert extracted_hash == sha256_file(source_path)
    assert output_path.is_file()
    assert not list(tmp_path.glob("*.building"))
    with EvidenceStore.open_read_only(output_path) as store:
        assert store.verify_snapshot("chembl36-pilot-v1")


def test_atomic_builder_refuses_to_overwrite_output(tmp_path: Path) -> None:
    source_path = tmp_path / "chembl_36.db"
    output_path = tmp_path / "evidence.sqlite"
    create_chembl_fixture(source_path)
    output_path.write_text("keep me", encoding="utf-8")
    with pytest.raises(EvidenceStoreError, match="refusing to overwrite"):
        build_snapshot(
            source_database=source_path,
            output_database=output_path,
            selection=selection(),
            snapshot_id="chembl36-pilot-v1",
            created_at="2026-10-24T00:00:00Z",
        )
    assert output_path.read_text(encoding="utf-8") == "keep me"


def test_selection_manifest_is_strict(tmp_path: Path) -> None:
    manifest = tmp_path / "selection.json"
    manifest.write_text(
        '{"molecule_chembl_ids":["CHEMBL941"],'
        '"target_chembl_ids":["CHEMBL1862"],"unexpected":true}',
        encoding="utf-8",
    )
    with pytest.raises(EvidenceStoreError, match="unknown selection-manifest fields"):
        load_selection(manifest)
