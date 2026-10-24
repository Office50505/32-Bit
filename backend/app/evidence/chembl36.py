import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.evidence.store import EvidenceStore, EvidenceStoreError, SnapshotSpec, _canonical_json

EXPECTED_RELEASE = "ChEMBL_36"
RELEASE_DOI = "10.6019/CHEMBL.database.36"
RELEASE_URI = (
    "https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_36/"
    "chembl_36_sqlite.tar.gz"
)
OFFICIAL_ARCHIVE_SHA256 = "b25820eef0f0481ad7712bdf4bac3b45f354e3cbacb76be1fdbf4205d6b48fb9"

_REQUIRED_TABLES = frozenset(
    {
        "activities",
        "assays",
        "component_sequences",
        "component_synonyms",
        "compound_records",
        "compound_structures",
        "docs",
        "molecule_dictionary",
        "molecule_hierarchy",
        "molecule_synonyms",
        "target_components",
        "target_dictionary",
        "version",
    }
)


class ChemblExtractionError(EvidenceStoreError):
    """Raised when a numbered ChEMBL source cannot satisfy the extraction contract."""


@dataclass(frozen=True, slots=True)
class Chembl36Selection:
    molecule_chembl_ids: tuple[str, ...]
    target_chembl_ids: tuple[str, ...]
    endpoints: tuple[str, ...] = ("IC50", "EC50", "Ki", "Kd")

    def __post_init__(self) -> None:
        if not self.molecule_chembl_ids:
            raise ValueError("at least one ChEMBL molecule ID is required")
        if not self.target_chembl_ids:
            raise ValueError("at least one ChEMBL target ID is required")
        if not self.endpoints:
            raise ValueError("at least one activity endpoint is required")
        for identifier in (*self.molecule_chembl_ids, *self.target_chembl_ids):
            if not identifier.startswith("CHEMBL") or not identifier[6:].isdigit():
                raise ValueError(f"invalid ChEMBL identifier: {identifier}")


@dataclass(frozen=True, slots=True)
class ChemblExtractionStats:
    molecules: int
    targets: int
    target_components: int
    papers: int
    assays: int
    activities: int


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _placeholders(values: tuple[str, ...]) -> str:
    return ",".join("?" for _ in values)


class Chembl36Extractor:
    """Extract a benchmark-scoped snapshot from the official ChEMBL 36 SQLite release."""

    def __init__(self, source_database: str | Path) -> None:
        self._source_path = Path(source_database).resolve()
        if not self._source_path.is_file():
            raise ChemblExtractionError(f"ChEMBL database does not exist: {self._source_path}")
        self._connection = sqlite3.connect(
            f"{self._source_path.as_uri()}?mode=ro&immutable=1",
            uri=True,
        )
        self._connection.row_factory = sqlite3.Row
        self._validate_source()

    def __enter__(self) -> "Chembl36Extractor":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _validate_source(self) -> None:
        integrity = self._connection.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise ChemblExtractionError(f"ChEMBL SQLite integrity check failed: {integrity}")
        tables = {
            row["name"]
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        missing = sorted(_REQUIRED_TABLES - tables)
        if missing:
            raise ChemblExtractionError(
                f"source is not a compatible ChEMBL database; missing tables: {missing}"
            )
        versions = {
            str(row["name"])
            for row in self._connection.execute("SELECT name FROM version")
        }
        if EXPECTED_RELEASE not in versions:
            found = ", ".join(sorted(versions)) or "no release marker"
            raise ChemblExtractionError(
                f"expected {EXPECTED_RELEASE}, but the database reports: {found}"
            )

    def extract(
        self,
        *,
        destination: EvidenceStore,
        snapshot_id: str,
        selection: Chembl36Selection,
        extracted_database_sha256: str,
        created_at: str,
        archive_sha256: str = OFFICIAL_ARCHIVE_SHA256,
    ) -> ChemblExtractionStats:
        molecule_rows = self._molecule_rows(selection.molecule_chembl_ids)
        target_rows = self._target_rows(selection.target_chembl_ids)
        self._require_complete_selection(
            requested=selection.molecule_chembl_ids,
            found={row["chembl_id"] for row in molecule_rows},
            entity="molecule",
        )
        self._require_complete_selection(
            requested=selection.target_chembl_ids,
            found={row["chembl_id"] for row in target_rows},
            entity="target",
        )

        destination.register_snapshot(
            SnapshotSpec(
                snapshot_id=snapshot_id,
                source_name="ChEMBL",
                source_version="36",
                source_sha256=archive_sha256,
                extracted_sha256=extracted_database_sha256,
                source_uri=RELEASE_URI,
                source_doi=RELEASE_DOI,
                license="CC BY-SA 3.0",
                scope={
                    "molecule_chembl_ids": list(selection.molecule_chembl_ids),
                    "target_chembl_ids": list(selection.target_chembl_ids),
                    "endpoints": list(selection.endpoints),
                },
                created_at=created_at,
            )
        )

        molecule_by_molregno = self._load_molecules(
            destination=destination,
            snapshot_id=snapshot_id,
            rows=molecule_rows,
        )
        target_by_tid, component_count = self._load_targets(
            destination=destination,
            snapshot_id=snapshot_id,
            rows=target_rows,
        )
        paper_count, assay_count, activity_count = self._load_activities(
            destination=destination,
            snapshot_id=snapshot_id,
            selection=selection,
            molecule_by_molregno=molecule_by_molregno,
            target_by_tid=target_by_tid,
        )
        return ChemblExtractionStats(
            molecules=len(molecule_rows),
            targets=len(target_rows),
            target_components=component_count,
            papers=paper_count,
            assays=assay_count,
            activities=activity_count,
        )

    @staticmethod
    def _require_complete_selection(
        *,
        requested: tuple[str, ...],
        found: set[str],
        entity: str,
    ) -> None:
        missing = sorted(set(requested) - found)
        if missing:
            raise ChemblExtractionError(
                f"selected {entity} IDs are absent from ChEMBL 36: {missing}"
            )

    def _molecule_rows(self, identifiers: tuple[str, ...]) -> list[sqlite3.Row]:
        return self._connection.execute(
            f"""
            SELECT md.molregno, md.pref_name, md.chembl_id,
                   cs.standard_inchi_key, cs.canonical_smiles,
                   parent_cs.standard_inchi_key AS parent_inchi_key
            FROM molecule_dictionary AS md
            JOIN compound_structures AS cs ON cs.molregno = md.molregno
            LEFT JOIN molecule_hierarchy AS mh ON mh.molregno = md.molregno
            LEFT JOIN compound_structures AS parent_cs
                   ON parent_cs.molregno = mh.parent_molregno
            WHERE md.chembl_id IN ({_placeholders(identifiers)})
            ORDER BY md.chembl_id
            """,
            identifiers,
        ).fetchall()

    def _target_rows(self, identifiers: tuple[str, ...]) -> list[sqlite3.Row]:
        return self._connection.execute(
            f"""
            SELECT tid, target_type, pref_name, organism, chembl_id
            FROM target_dictionary
            WHERE chembl_id IN ({_placeholders(identifiers)})
            ORDER BY chembl_id
            """,
            identifiers,
        ).fetchall()

    def _load_molecules(
        self,
        *,
        destination: EvidenceStore,
        snapshot_id: str,
        rows: list[sqlite3.Row],
    ) -> dict[int, str]:
        mapping: dict[int, str] = {}
        for row in rows:
            if not row["standard_inchi_key"] or not row["canonical_smiles"]:
                raise ChemblExtractionError(
                    f"selected molecule has no usable small-molecule structure: {row['chembl_id']}"
                )
            payload = dict(row)
            destination.add_molecule(
                snapshot_id=snapshot_id,
                inchikey=row["standard_inchi_key"],
                canonical_smiles=row["canonical_smiles"],
                parent_inchikey=row["parent_inchi_key"],
                preferred_name=row["pref_name"],
                chembl_id=row["chembl_id"],
                raw_record_sha256=_record_sha256(payload),
            )
            mapping[int(row["molregno"])] = row["standard_inchi_key"]

            aliases = self._molecule_aliases(int(row["molregno"]), row["pref_name"])
            seen: set[tuple[str, str]] = set()
            for alias, source in aliases:
                normalized = alias.casefold().strip()
                if not normalized or (normalized, source) in seen:
                    continue
                destination.add_molecule_alias(
                    snapshot_id=snapshot_id,
                    inchikey=row["standard_inchi_key"],
                    alias=alias,
                    source=source,
                )
                seen.add((normalized, source))
        return mapping

    def _molecule_aliases(self, molregno: int, preferred_name: str | None) -> list[tuple[str, str]]:
        aliases: list[tuple[str, str]] = []
        if preferred_name:
            aliases.append((preferred_name, "CHEMBL_PREF_NAME"))
        aliases.extend(
            (row["synonyms"], f"CHEMBL_SYNONYM:{row['syn_type']}")
            for row in self._connection.execute(
                """
                SELECT synonyms, syn_type FROM molecule_synonyms
                WHERE molregno = ? AND synonyms IS NOT NULL
                ORDER BY molsyn_id
                """,
                (molregno,),
            )
        )
        aliases.extend(
            (row["compound_name"], "CHEMBL_COMPOUND_RECORD")
            for row in self._connection.execute(
                """
                SELECT compound_name FROM compound_records
                WHERE molregno = ? AND compound_name IS NOT NULL
                ORDER BY record_id
                """,
                (molregno,),
            )
        )
        return aliases

    def _load_targets(
        self,
        *,
        destination: EvidenceStore,
        snapshot_id: str,
        rows: list[sqlite3.Row],
    ) -> tuple[dict[int, str], int]:
        mapping: dict[int, str] = {}
        component_count = 0
        for row in rows:
            components = self._connection.execute(
                """
                SELECT tc.component_id, tc.homologue, cs.accession, cs.component_type,
                       cs.description, cs.organism
                FROM target_components AS tc
                JOIN component_sequences AS cs USING (component_id)
                WHERE tc.tid = ?
                ORDER BY tc.component_id
                """,
                (row["tid"],),
            ).fetchall()
            synonyms = self._target_synonyms(int(row["tid"]))
            gene_symbols = sorted(
                {
                    alias
                    for alias, syn_type in synonyms
                    if syn_type == "GENE_SYMBOL"
                }
            )
            accessions = sorted(
                {component["accession"] for component in components if component["accession"]}
            )
            payload = {
                "target": dict(row),
                "components": [dict(component) for component in components],
                "synonyms": synonyms,
            }
            destination.add_target(
                snapshot_id=snapshot_id,
                target_id=row["chembl_id"],
                preferred_name=row["pref_name"],
                organism=row["organism"],
                target_type=row["target_type"],
                accession=accessions[0] if len(accessions) == 1 else None,
                gene_symbol=gene_symbols[0] if len(gene_symbols) == 1 else None,
                raw_record_sha256=_record_sha256(payload),
            )
            mapping[int(row["tid"])] = row["chembl_id"]
            for component in components:
                destination.add_target_component(
                    snapshot_id=snapshot_id,
                    target_id=row["chembl_id"],
                    component_id=int(component["component_id"]),
                    accession=component["accession"],
                    component_type=component["component_type"],
                    description=component["description"],
                    organism=component["organism"],
                    homologue=int(component["homologue"]),
                    raw_record_sha256=_record_sha256(dict(component)),
                )
                component_count += 1
            aliases = [(row["pref_name"], "CHEMBL_PREF_NAME")]
            aliases.extend((alias, f"CHEMBL_COMPONENT:{syn_type}") for alias, syn_type in synonyms)
            seen: set[tuple[str, str]] = set()
            for alias, source in aliases:
                normalized = alias.casefold().strip()
                if not normalized or (normalized, source) in seen:
                    continue
                destination.add_target_alias(
                    snapshot_id=snapshot_id,
                    target_id=row["chembl_id"],
                    alias=alias,
                    source=source,
                )
                seen.add((normalized, source))
        return mapping, component_count

    def _target_synonyms(self, tid: int) -> list[tuple[str, str]]:
        return [
            (row["component_synonym"], row["syn_type"])
            for row in self._connection.execute(
                """
                SELECT DISTINCT csyn.component_synonym, csyn.syn_type
                FROM target_components AS tc
                JOIN component_synonyms AS csyn USING (component_id)
                WHERE tc.tid = ? AND csyn.component_synonym IS NOT NULL
                ORDER BY csyn.component_synonym, csyn.syn_type
                """,
                (tid,),
            )
        ]

    def _activity_rows(self, selection: Chembl36Selection) -> list[sqlite3.Row]:
        parameters = (
            *selection.molecule_chembl_ids,
            *selection.target_chembl_ids,
            *selection.endpoints,
        )
        return self._connection.execute(
            f"""
            SELECT act.activity_id, act.assay_id, act.molregno, act.type,
                   act.relation, act.value, act.units, act.text_value,
                   act.standard_type, act.standard_relation, act.standard_value,
                   act.standard_units, act.standard_text_value, act.pchembl_value,
                   act.activity_comment, act.data_validity_comment,
                   act.potential_duplicate,
                   ass.chembl_id AS assay_chembl_id, ass.description,
                   ass.assay_type, ass.assay_test_type, ass.assay_category,
                   ass.assay_organism, ass.assay_strain, ass.assay_tissue,
                   ass.assay_cell_type, ass.assay_subcellular_fraction,
                   ass.relationship_type, ass.confidence_score, ass.bao_format,
                   ass.variant_id, ass.assay_group, ass.tid,
                   doc.chembl_id AS document_chembl_id, doc.pubmed_id,
                   doc.doi, doc.title, doc.doc_type
            FROM activities AS act
            JOIN assays AS ass ON ass.assay_id = act.assay_id
            JOIN molecule_dictionary AS md ON md.molregno = act.molregno
            JOIN target_dictionary AS td ON td.tid = ass.tid
            LEFT JOIN docs AS doc ON doc.doc_id = ass.doc_id
            WHERE md.chembl_id IN ({_placeholders(selection.molecule_chembl_ids)})
              AND td.chembl_id IN ({_placeholders(selection.target_chembl_ids)})
              AND act.standard_type IN ({_placeholders(selection.endpoints)})
            ORDER BY act.activity_id
            """,
            parameters,
        ).fetchall()

    def _load_activities(
        self,
        *,
        destination: EvidenceStore,
        snapshot_id: str,
        selection: Chembl36Selection,
        molecule_by_molregno: dict[int, str],
        target_by_tid: dict[int, str],
    ) -> tuple[int, int, int]:
        rows = self._activity_rows(selection)
        loaded_papers: set[str] = set()
        loaded_assays: set[str] = set()
        for row in rows:
            paper_id = row["document_chembl_id"]
            if paper_id and paper_id not in loaded_papers:
                paper_payload = {
                    key: row[key]
                    for key in (
                        "document_chembl_id",
                        "pubmed_id",
                        "doi",
                        "title",
                        "doc_type",
                    )
                }
                destination.add_paper(
                    snapshot_id=snapshot_id,
                    paper_id=paper_id,
                    pmid=str(row["pubmed_id"]) if row["pubmed_id"] is not None else None,
                    doi=row["doi"],
                    title=row["title"],
                    retraction_status="UNKNOWN",
                    raw_record_sha256=_record_sha256(paper_payload),
                )
                loaded_papers.add(paper_id)

            assay_id = row["assay_chembl_id"]
            if assay_id not in loaded_assays:
                assay_payload = {
                    key: row[key]
                    for key in (
                        "assay_id",
                        "assay_chembl_id",
                        "description",
                        "assay_type",
                        "assay_test_type",
                        "assay_category",
                        "assay_organism",
                        "assay_strain",
                        "assay_tissue",
                        "assay_cell_type",
                        "assay_subcellular_fraction",
                        "relationship_type",
                        "confidence_score",
                        "bao_format",
                        "variant_id",
                        "assay_group",
                        "tid",
                    )
                }
                destination.add_assay(
                    snapshot_id=snapshot_id,
                    assay_id=assay_id,
                    source="CHEMBL",
                    target_id=target_by_tid[int(row["tid"])],
                    organism=row["assay_organism"],
                    assay_type=row["assay_type"],
                    description=row["description"],
                    conditions={
                        "test_type": row["assay_test_type"],
                        "category": row["assay_category"],
                        "strain": row["assay_strain"],
                        "tissue": row["assay_tissue"],
                        "cell_type": row["assay_cell_type"],
                        "subcellular_fraction": row["assay_subcellular_fraction"],
                        "relationship_type": row["relationship_type"],
                        "bao_format": row["bao_format"],
                        "variant_id": row["variant_id"],
                        "assay_group": row["assay_group"],
                    },
                    target_confidence_score=row["confidence_score"],
                    paper_id=paper_id,
                    raw_record_sha256=_record_sha256(assay_payload),
                )
                loaded_assays.add(assay_id)

            activity_payload = dict(row)
            destination.add_activity(
                snapshot_id=snapshot_id,
                activity_id=str(row["activity_id"]),
                assay_id=assay_id,
                molecule_inchikey=molecule_by_molregno[int(row["molregno"])],
                measurement_type=row["standard_type"] or row["type"],
                original_value=row["value"],
                original_unit=row["units"],
                original_relation=row["relation"],
                original_text_value=row["text_value"],
                standard_value=row["standard_value"],
                standard_unit=row["standard_units"],
                standard_relation=row["standard_relation"],
                standard_text_value=row["standard_text_value"],
                pchembl_value=row["pchembl_value"],
                activity_outcome=row["activity_comment"],
                data_validity_comment=row["data_validity_comment"],
                potential_duplicate=bool(row["potential_duplicate"]),
                raw_record_sha256=_record_sha256(activity_payload),
            )
        return len(loaded_papers), len(loaded_assays), len(rows)
