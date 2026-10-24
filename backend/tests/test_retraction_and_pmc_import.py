from pathlib import Path

import pytest

from app.evidence import EvidenceStore, EvidenceStoreError, SnapshotSpec
from app.evidence.pmc import import_jats_article, import_pmc_snapshot, read_pmc_xml_files
from app.evidence.retractions import FrozenRetractionIndex, normalize_doi, normalize_pmid
from app.models.evidence_assistant import RetractionStatus

HASH = "a" * 64

CSV_TEXT = (
    "Record ID,RetractionDate,OriginalPaperDOI,OriginalPaperPubMedID,"
    "RetractionNature,Reason\n"
    "1,01/01/2020,10.1000/retracted,00012345,Retraction,Unreliable data\n"
    "2,01/01/2021,10.1000/retracted,00012345,Reinstatement,Review complete\n"
    "3,02/02/2022,https://doi.org/10.1000/concern,555,Expression of Concern,Investigation\n"
    "4,03/03/2023,doi:10.1000/corrected,666,Correction,Results corrected\n"
    "5,04/04/2024,,,Retraction,No identifiers\n"
)

JATS_XML = (
    b"""<?xml version="1.0" encoding="UTF-8"?>
<article>
  <front>
    <article-meta>
      <article-id pub-id-type="pmcid">PMC123</article-id>
      <article-id pub-id-type="pmid">12345</article-id>
      <article-id pub-id-type="doi">10.1000/retracted</article-id>
      <title-group><article-title>Imatinib and <italic>ABL1</italic></article-title></title-group>
      <permissions><license license-type="cc-by"><license-p>Creative Commons.</license-p>"""
    b"""</license></permissions>
      <abstract><p>Imatinib was evaluated against ABL1.</p></abstract>
    </article-meta>
  </front>
  <body>
    <sec><title>Results</title>
      <p>Imatinib inhibited ABL1 in the biochemical assay. The measured IC50 was 42 nM.</p>
      <fig><caption><p>This figure caption must not become evidence.</p></caption></fig>
    </sec>
    <sec><title>Discussion</title><p>The result requires independent replication.</p></sec>
  </body>
</article>
"""
)


@pytest.fixture
def retraction_csv(tmp_path: Path) -> Path:
    path = tmp_path / "retraction_watch.csv"
    path.write_text(CSV_TEXT, encoding="utf-8")
    return path


def test_identifier_normalization_is_stable() -> None:
    assert normalize_doi(" HTTPS://DOI.ORG/10.1000/ABC ") == "10.1000/abc"
    assert normalize_pmid("00012345") == "12345"
    assert normalize_pmid("00000000") is None


def test_retraction_index_uses_later_reinstatement_and_other_notice_types(
    retraction_csv: Path,
) -> None:
    index = FrozenRetractionIndex.from_csv(retraction_csv)
    assert len(index.records) == 4
    assert index.status_for(doi="10.1000/retracted") == RetractionStatus.REINSTATED
    assert index.status_for(pmid="555") == RetractionStatus.EXPRESSION_OF_CONCERN
    assert index.status_for(doi="10.1000/corrected") == RetractionStatus.CORRECTED
    assert index.status_for(doi="10.1000/clear") == RetractionStatus.CLEAR
    assert len(index.source_sha256) == 64


def test_retraction_snapshot_is_sealed_and_traceable(
    tmp_path: Path,
    retraction_csv: Path,
) -> None:
    index = FrozenRetractionIndex.from_csv(retraction_csv)
    with EvidenceStore.create(tmp_path / "evidence.sqlite") as store:
        content_hash = index.import_snapshot(
            store,
            snapshot_id="retractions-2026-10-24",
            source_version="2026-10-24",
            source_uri="https://gitlab.com/crossref/retraction-watch-data",
            created_at="2026-10-24T00:00:00Z",
        )
        assert store.verify_snapshot("retractions-2026-10-24")
        assert store.verified_snapshot_hash("retractions-2026-10-24") == content_hash
        rows = store._connection.execute(  # noqa: SLF001 - verifies frozen source mapping
            "SELECT * FROM retractions ORDER BY retraction_id"
        ).fetchall()
        assert rows[0]["retraction_id"] == "RW:1"
        assert rows[0]["doi"] == "10.1000/retracted"
        assert rows[0]["raw_record_sha256"] == index.records[0].raw_record_sha256


def test_jats_import_preserves_precise_passages_and_retraction_status(
    tmp_path: Path,
    retraction_csv: Path,
) -> None:
    index = FrozenRetractionIndex.from_csv(retraction_csv)
    with EvidenceStore.create(tmp_path / "evidence.sqlite") as store:
        store.register_snapshot(
            SnapshotSpec(
                snapshot_id="pmc-pilot-v1",
                source_name="Europe PMC OA",
                source_version="2026-10-24",
                source_sha256=HASH,
                scope={"pmcids": ["PMC123"]},
                created_at="2026-10-24T00:00:00Z",
            )
        )
        result = import_jats_article(
            store,
            snapshot_id="pmc-pilot-v1",
            xml_bytes=JATS_XML,
            retraction_index=index,
            maximum_passage_characters=200,
        )
        assert result.metadata.pmcid == "PMC123"
        assert result.metadata.title == "Imatinib and ABL1"
        assert result.metadata.article_license == "cc-by: Creative Commons."
        assert result.retraction_status == RetractionStatus.REINSTATED
        assert result.passage_count == 3

        paper = store._connection.execute(  # noqa: SLF001 - verifies imported provenance
            "SELECT * FROM papers WHERE paper_id = 'PMCID:PMC123'"
        ).fetchone()
        assert paper["retraction_status"] == "REINSTATED"
        passages = store._connection.execute(  # noqa: SLF001
            "SELECT * FROM passages ORDER BY priority, passage_id"
        ).fetchall()
        texts = [row["passage_text"] for row in passages]
        assert "Imatinib was evaluated against ABL1." in texts
        assert any("measured IC50 was 42 nM" in text for text in texts)
        assert not any("figure caption" in text for text in texts)
        results = next(row for row in passages if row["section_name"] == "Results")
        assert results["paragraph_number"] == 1
        assert results["sentence_start"] == 0
        assert results["priority"] == 1
        assert len(results["passage_sha256"]) == 64


def test_jats_entity_declarations_are_rejected_before_parsing(
    tmp_path: Path,
    retraction_csv: Path,
) -> None:
    index = FrozenRetractionIndex.from_csv(retraction_csv)
    malicious = b'<!DOCTYPE article [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><article/>'
    with EvidenceStore.create(tmp_path / "evidence.sqlite") as store:
        store.register_snapshot(
            SnapshotSpec(
                snapshot_id="pmc-pilot-v1",
                source_name="Europe PMC OA",
                source_version="1",
                source_sha256=HASH,
                scope={},
                created_at="2026-10-24T00:00:00Z",
            )
        )
        with pytest.raises(EvidenceStoreError, match="entity declarations"):
            import_jats_article(
                store,
                snapshot_id="pmc-pilot-v1",
                xml_bytes=malicious,
                retraction_index=index,
            )


def test_retraction_csv_requires_expected_columns(tmp_path: Path) -> None:
    path = tmp_path / "invalid.csv"
    path.write_text("Record ID,RetractionNature\n1,Retraction\n", encoding="utf-8")
    with pytest.raises(EvidenceStoreError, match="missing required columns"):
        FrozenRetractionIndex.from_csv(path)


def test_pmc_snapshot_import_is_sealed_and_file_selection_is_exact(
    tmp_path: Path,
    retraction_csv: Path,
) -> None:
    index = FrozenRetractionIndex.from_csv(retraction_csv)
    source_directory = tmp_path / "pmc"
    source_directory.mkdir()
    (source_directory / "PMC123.xml").write_bytes(JATS_XML)
    articles = read_pmc_xml_files(source_directory, ("PMC123",))
    with EvidenceStore.create(tmp_path / "evidence.sqlite") as store:
        result = import_pmc_snapshot(
            store,
            snapshot_id="pmc-pilot-v1",
            source_version="retrieved-2026-10-24",
            created_at="2026-10-24T00:00:00Z",
            articles=articles,
            retraction_index=index,
            maximum_passage_characters=200,
        )
        assert result.article_count == 1
        assert result.passage_count == 3
        assert store.verify_snapshot("pmc-pilot-v1")
        assert store.verified_snapshot_hash("pmc-pilot-v1") == result.content_sha256

    with pytest.raises(EvidenceStoreError, match="missing frozen Europe PMC XML"):
        read_pmc_xml_files(source_directory, ("PMC123", "PMC999"))
    with pytest.raises(ValueError, match="invalid PMCID"):
        read_pmc_xml_files(source_directory, ("123",))
