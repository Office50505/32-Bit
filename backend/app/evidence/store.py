import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from app.evidence.schema import SCHEMA_SQL, SCHEMA_VERSION
from app.models.evidence_assistant import EvidenceItem


class EvidenceStoreError(RuntimeError):
    """Base error for evidence-store contract violations."""


class SnapshotSealedError(EvidenceStoreError):
    """Raised when a builder attempts to mutate a sealed snapshot."""


@dataclass(frozen=True, slots=True)
class SnapshotSpec:
    snapshot_id: str
    source_name: str
    source_version: str
    source_sha256: str
    scope: dict[str, Any]
    created_at: str
    extracted_sha256: str | None = None
    source_uri: str | None = None
    source_doi: str | None = None
    license: str | None = None


@dataclass(frozen=True, slots=True)
class PassageSearchHit:
    passage_id: str
    snapshot_id: str
    article_title: str | None
    section_name: str
    passage_text: str
    snippet: str
    bm25_score: float
    priority: int


_CONTENT_TABLE_KEYS: dict[str, tuple[str, ...]] = {
    "molecules": ("inchikey",),
    "molecule_aliases": ("inchikey", "normalized_alias", "source"),
    "targets": ("target_id",),
    "target_aliases": ("target_id", "normalized_alias", "source"),
    "target_components": ("target_id", "component_id"),
    "papers": ("paper_id",),
    "assays": ("assay_id",),
    "activities": ("activity_id",),
    "passages": ("passage_id",),
    "retractions": ("retraction_id",),
    "run_records": ("record_id",),
    "evidence_items": ("evidence_id",),
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _normalized_hash(value: str) -> str:
    digest = value.removeprefix("sha256:")
    invalid_hash = len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    )
    if invalid_hash:
        raise EvidenceStoreError("record hashes must be lowercase SHA-256 digests")
    return digest


class EvidenceStore:
    """SQLite-backed frozen evidence store.

    Snapshot-building code opens a writable store, loads records, and seals each
    snapshot. Claim checking opens the completed database with ``read_only=True``.
    """

    def __init__(self, connection: sqlite3.Connection, *, read_only: bool) -> None:
        self._connection = connection
        self._read_only = read_only
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        if read_only:
            self._connection.execute("PRAGMA query_only = ON")

    @classmethod
    def create(cls, path: str | Path) -> Self:
        database_path = Path(path).resolve()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database_path)
        store = cls(connection, read_only=False)
        store._initialize_schema()
        return store

    @classmethod
    def open_read_only(cls, path: str | Path) -> Self:
        database_path = Path(path).resolve()
        if not database_path.is_file():
            raise EvidenceStoreError(f"evidence database does not exist: {database_path}")
        connection = sqlite3.connect(f"{database_path.as_uri()}?mode=ro&immutable=1", uri=True)
        store = cls(connection, read_only=True)
        store._require_supported_schema()
        return store

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _initialize_schema(self) -> None:
        self._require_writable()
        current_version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if current_version > SCHEMA_VERSION:
            raise EvidenceStoreError(
                f"database schema {current_version} is newer than supported {SCHEMA_VERSION}"
            )
        if current_version == 0:
            try:
                self._connection.executescript(SCHEMA_SQL)
            except sqlite3.OperationalError as error:
                if "fts5" in str(error).lower():
                    raise EvidenceStoreError("this SQLite build does not provide FTS5") from error
                raise
            self._connection.execute(
                "INSERT INTO schema_migrations(version, description) VALUES (?, ?)",
                (SCHEMA_VERSION, "initial structured-first evidence schema"),
            )
            self._connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._connection.commit()
        self._require_supported_schema()

    def _require_supported_schema(self) -> None:
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version != SCHEMA_VERSION:
            raise EvidenceStoreError(
                f"unsupported evidence schema {version}; expected {SCHEMA_VERSION}"
            )

    def _require_writable(self) -> None:
        if self._read_only:
            raise EvidenceStoreError("claim-checking stores are read-only")

    def _require_snapshot_writable(self, snapshot_id: str) -> None:
        self._require_writable()
        row = self._connection.execute(
            "SELECT sealed FROM snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise EvidenceStoreError(f"unknown snapshot: {snapshot_id}")
        if row["sealed"]:
            raise SnapshotSealedError(f"snapshot is sealed: {snapshot_id}")

    def register_snapshot(self, snapshot: SnapshotSpec) -> None:
        self._require_writable()
        source_hash = _normalized_hash(snapshot.source_sha256)
        self._connection.execute(
            """
            INSERT INTO snapshots(
                snapshot_id, source_name, source_version, source_sha256,
                extracted_sha256, source_uri, source_doi, license,
                scope_json, created_at, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.snapshot_id,
                snapshot.source_name,
                snapshot.source_version,
                source_hash,
                (
                    _normalized_hash(snapshot.extracted_sha256)
                    if snapshot.extracted_sha256 is not None
                    else None
                ),
                snapshot.source_uri,
                snapshot.source_doi,
                snapshot.license,
                _canonical_json(snapshot.scope),
                snapshot.created_at,
                SCHEMA_VERSION,
            ),
        )
        self._connection.commit()

    def add_molecule(
        self,
        *,
        snapshot_id: str,
        inchikey: str,
        canonical_smiles: str,
        raw_record_sha256: str,
        parent_inchikey: str | None = None,
        preferred_name: str | None = None,
        chembl_id: str | None = None,
        pubchem_cid: int | None = None,
    ) -> None:
        self._require_snapshot_writable(snapshot_id)
        self._connection.execute(
            """
            INSERT INTO molecules VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                inchikey,
                canonical_smiles,
                parent_inchikey,
                preferred_name,
                chembl_id,
                pubchem_cid,
                _normalized_hash(raw_record_sha256),
            ),
        )
        self._connection.commit()

    def add_molecule_alias(
        self,
        *,
        snapshot_id: str,
        inchikey: str,
        alias: str,
        source: str,
    ) -> None:
        self._require_snapshot_writable(snapshot_id)
        self._connection.execute(
            "INSERT INTO molecule_aliases VALUES (?, ?, ?, ?, ?)",
            (snapshot_id, inchikey, alias, alias.casefold().strip(), source),
        )
        self._connection.commit()

    def add_target(
        self,
        *,
        snapshot_id: str,
        target_id: str,
        preferred_name: str,
        raw_record_sha256: str,
        organism: str | None = None,
        target_type: str | None = None,
        accession: str | None = None,
        gene_symbol: str | None = None,
    ) -> None:
        self._require_snapshot_writable(snapshot_id)
        self._connection.execute(
            "INSERT INTO targets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                target_id,
                preferred_name,
                organism,
                target_type,
                accession,
                gene_symbol,
                _normalized_hash(raw_record_sha256),
            ),
        )
        self._connection.commit()

    def add_target_alias(
        self,
        *,
        snapshot_id: str,
        target_id: str,
        alias: str,
        source: str,
    ) -> None:
        self._require_snapshot_writable(snapshot_id)
        self._connection.execute(
            "INSERT INTO target_aliases VALUES (?, ?, ?, ?, ?)",
            (snapshot_id, target_id, alias, alias.casefold().strip(), source),
        )
        self._connection.commit()

    def add_target_component(
        self,
        *,
        snapshot_id: str,
        target_id: str,
        component_id: int,
        raw_record_sha256: str,
        accession: str | None = None,
        component_type: str | None = None,
        description: str | None = None,
        organism: str | None = None,
        homologue: int = 0,
    ) -> None:
        self._require_snapshot_writable(snapshot_id)
        self._connection.execute(
            "INSERT INTO target_components VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                target_id,
                component_id,
                accession,
                component_type,
                description,
                organism,
                homologue,
                _normalized_hash(raw_record_sha256),
            ),
        )
        self._connection.commit()

    def add_paper(
        self,
        *,
        snapshot_id: str,
        paper_id: str,
        title: str | None,
        retraction_status: str,
        raw_record_sha256: str,
        pmcid: str | None = None,
        pmid: str | None = None,
        doi: str | None = None,
        article_license: str | None = None,
    ) -> None:
        self._require_snapshot_writable(snapshot_id)
        self._connection.execute(
            "INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                paper_id,
                pmcid,
                pmid,
                doi,
                title,
                article_license,
                retraction_status,
                _normalized_hash(raw_record_sha256),
            ),
        )
        self._connection.commit()

    def add_assay(
        self,
        *,
        snapshot_id: str,
        assay_id: str,
        source: str,
        description: str | None,
        raw_record_sha256: str,
        target_id: str | None = None,
        organism: str | None = None,
        assay_type: str | None = None,
        conditions: dict[str, Any] | None = None,
        target_confidence_score: int | None = None,
        paper_id: str | None = None,
    ) -> None:
        self._require_snapshot_writable(snapshot_id)
        self._connection.execute(
            "INSERT INTO assays VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                assay_id,
                source,
                target_id,
                organism,
                assay_type,
                description,
                _canonical_json(conditions or {}),
                target_confidence_score,
                paper_id,
                _normalized_hash(raw_record_sha256),
            ),
        )
        self._connection.commit()

    def add_activity(
        self,
        *,
        snapshot_id: str,
        activity_id: str,
        assay_id: str,
        molecule_inchikey: str,
        measurement_type: str,
        raw_record_sha256: str,
        original_value: float | None = None,
        original_unit: str | None = None,
        original_relation: str | None = None,
        original_text_value: str | None = None,
        standard_value: float | None = None,
        standard_unit: str | None = None,
        standard_relation: str | None = None,
        standard_text_value: str | None = None,
        pchembl_value: float | None = None,
        activity_outcome: str | None = None,
        data_validity_comment: str | None = None,
        potential_duplicate: bool = False,
    ) -> None:
        self._require_snapshot_writable(snapshot_id)
        self._connection.execute(
            """
            INSERT INTO activities VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                snapshot_id,
                activity_id,
                assay_id,
                molecule_inchikey,
                measurement_type,
                original_value,
                original_unit,
                original_relation,
                original_text_value,
                standard_value,
                standard_unit,
                standard_relation,
                standard_text_value,
                pchembl_value,
                activity_outcome,
                data_validity_comment,
                int(potential_duplicate),
                _normalized_hash(raw_record_sha256),
            ),
        )
        self._connection.commit()

    def add_passage(
        self,
        *,
        snapshot_id: str,
        passage_id: str,
        paper_id: str,
        section_name: str,
        passage_text: str,
        passage_sha256: str,
        paragraph_number: int | None = None,
        sentence_start: int | None = None,
        sentence_end: int | None = None,
        priority: int = 5,
    ) -> None:
        self._require_snapshot_writable(snapshot_id)
        paper = self._connection.execute(
            "SELECT title FROM papers WHERE snapshot_id = ? AND paper_id = ?",
            (snapshot_id, paper_id),
        ).fetchone()
        if paper is None:
            raise EvidenceStoreError(f"unknown paper: {paper_id}")
        try:
            self._connection.execute("BEGIN")
            self._connection.execute(
                "INSERT INTO passages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot_id,
                    passage_id,
                    paper_id,
                    section_name,
                    paragraph_number,
                    sentence_start,
                    sentence_end,
                    passage_text,
                    _normalized_hash(passage_sha256),
                    priority,
                ),
            )
            self._connection.execute(
                "INSERT INTO passages_fts VALUES (?, ?, ?, ?, ?)",
                (passage_id, snapshot_id, paper["title"], section_name, passage_text),
            )
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise

    def add_retraction(
        self,
        *,
        snapshot_id: str,
        retraction_id: str,
        notice_type: str,
        raw_record_sha256: str,
        doi: str | None = None,
        pmid: str | None = None,
        notice_date: str | None = None,
        reason: str | None = None,
    ) -> None:
        self._require_snapshot_writable(snapshot_id)
        self._connection.execute(
            "INSERT INTO retractions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                retraction_id,
                doi,
                pmid,
                notice_type,
                notice_date,
                reason,
                _normalized_hash(raw_record_sha256),
            ),
        )
        self._connection.commit()

    def add_run_record(
        self,
        *,
        snapshot_id: str,
        record_id: str,
        analysis_id: str,
        property_key: str,
        value: Any,
        manifest: dict[str, Any],
        raw_record_sha256: str,
        molecule_inchikey: str | None = None,
        unit: str | None = None,
    ) -> None:
        self._require_snapshot_writable(snapshot_id)
        self._connection.execute(
            "INSERT INTO run_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                record_id,
                analysis_id,
                molecule_inchikey,
                property_key,
                _canonical_json(value),
                unit,
                _canonical_json(manifest),
                _normalized_hash(raw_record_sha256),
            ),
        )
        self._connection.commit()

    def add_evidence_item(self, item: EvidenceItem) -> None:
        self._require_snapshot_writable(item.snapshot_id)
        self._connection.execute(
            """
            INSERT INTO evidence_items VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                item.evidence_id,
                item.snapshot_id,
                item.source_type.value,
                item.source_record_id,
                item.basis.value,
                item.molecule_inchikey,
                item.target_id,
                item.endpoint,
                item.relation,
                item.value,
                item.unit,
                item.paper_id,
                item.retraction_status.value,
                _normalized_hash(item.raw_record_sha256),
                _canonical_json(item.model_dump(mode="json")),
            ),
        )
        self._connection.commit()

    def resolve_molecule_alias(self, snapshot_id: str, alias: str) -> list[sqlite3.Row]:
        return self._connection.execute(
            """
            SELECT molecules.*
            FROM molecule_aliases
            JOIN molecules USING (snapshot_id, inchikey)
            WHERE snapshot_id = ? AND normalized_alias = ?
            ORDER BY inchikey
            """,
            (snapshot_id, alias.casefold().strip()),
        ).fetchall()

    def resolve_target_alias(self, snapshot_id: str, alias: str) -> list[sqlite3.Row]:
        return self._connection.execute(
            """
            SELECT targets.*
            FROM target_aliases
            JOIN targets USING (snapshot_id, target_id)
            WHERE snapshot_id = ? AND normalized_alias = ?
            ORDER BY target_id
            """,
            (snapshot_id, alias.casefold().strip()),
        ).fetchall()

    def structured_activity_search(
        self,
        *,
        snapshot_id: str,
        molecule_inchikey: str,
        target_id: str,
        endpoint: str | None = None,
        organism: str | None = None,
        limit: int = 100,
    ) -> list[sqlite3.Row]:
        if not 1 <= limit <= 1_000:
            raise EvidenceStoreError("activity-search limit must be between 1 and 1000")
        clauses = [
            "activities.snapshot_id = ?",
            "activities.molecule_inchikey = ?",
            "assays.target_id = ?",
        ]
        parameters: list[Any] = [snapshot_id, molecule_inchikey, target_id]
        if endpoint is not None:
            clauses.append("activities.measurement_type = ?")
            parameters.append(endpoint)
        if organism is not None:
            clauses.append("assays.organism = ?")
            parameters.append(organism)
        parameters.append(limit)
        return self._connection.execute(
            f"""
            SELECT activities.*, assays.source, assays.organism, assays.assay_type,
                   assays.description, assays.target_confidence_score, assays.paper_id
            FROM activities
            JOIN assays USING (snapshot_id, assay_id)
            WHERE {' AND '.join(clauses)}
            ORDER BY
                activities.data_validity_comment IS NOT NULL,
                activities.potential_duplicate,
                assays.target_confidence_score DESC,
                activities.activity_id
            LIMIT ?
            """,
            parameters,
        ).fetchall()

    def search_passages(
        self,
        *,
        snapshot_id: str,
        query: str,
        limit: int = 10,
    ) -> list[PassageSearchHit]:
        if not query.strip():
            raise EvidenceStoreError("passage query cannot be blank")
        if not 1 <= limit <= 50:
            raise EvidenceStoreError("passage-search limit must be between 1 and 50")
        rows = self._connection.execute(
            """
            SELECT passages_fts.passage_id, passages_fts.snapshot_id,
                   passages_fts.article_title, passages_fts.section_name,
                   passages_fts.passage_text, passages.priority,
                   snippet(passages_fts, 4, '<mark>', '</mark>', ' … ', 24) AS snippet,
                   bm25(passages_fts, 0.0, 0.0, 1.0, 1.5, 2.0) AS bm25_score
            FROM passages_fts
            JOIN passages
              ON passages.snapshot_id = passages_fts.snapshot_id
             AND passages.passage_id = passages_fts.passage_id
            WHERE passages_fts MATCH ? AND passages_fts.snapshot_id = ?
            ORDER BY passages.priority, bm25_score, passages_fts.passage_id
            LIMIT ?
            """,
            (query, snapshot_id, limit),
        ).fetchall()
        return [
            PassageSearchHit(
                passage_id=row["passage_id"],
                snapshot_id=row["snapshot_id"],
                article_title=row["article_title"],
                section_name=row["section_name"],
                passage_text=row["passage_text"],
                snippet=row["snippet"],
                bm25_score=row["bm25_score"],
                priority=row["priority"],
            )
            for row in rows
        ]

    def content_sha256(self, snapshot_id: str) -> str:
        snapshot = self._connection.execute(
            """
            SELECT snapshot_id, source_name, source_version, source_sha256,
                   extracted_sha256, source_uri, source_doi, license,
                   scope_json, created_at, schema_version
            FROM snapshots WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchone()
        if snapshot is None:
            raise EvidenceStoreError(f"unknown snapshot: {snapshot_id}")
        digest = hashlib.sha256()
        digest.update(_canonical_json(dict(snapshot)).encode("utf-8"))
        digest.update(b"\n")
        for table_name, order_keys in _CONTENT_TABLE_KEYS.items():
            order_clause = ", ".join(order_keys)
            rows = self._connection.execute(
                f"SELECT * FROM {table_name} WHERE snapshot_id = ? ORDER BY {order_clause}",
                (snapshot_id,),
            )
            for row in rows:
                digest.update(table_name.encode("ascii"))
                digest.update(b"\0")
                digest.update(_canonical_json(dict(row)).encode("utf-8"))
                digest.update(b"\n")
        return digest.hexdigest()

    def seal_snapshot(self, snapshot_id: str) -> str:
        self._require_snapshot_writable(snapshot_id)
        content_hash = self.content_sha256(snapshot_id)
        self._connection.execute(
            "UPDATE snapshots SET sealed = 1, content_sha256 = ? WHERE snapshot_id = ?",
            (content_hash, snapshot_id),
        )
        self._connection.commit()
        return content_hash

    def verify_snapshot(self, snapshot_id: str) -> bool:
        row = self._connection.execute(
            "SELECT sealed, content_sha256 FROM snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise EvidenceStoreError(f"unknown snapshot: {snapshot_id}")
        if not row["sealed"] or row["content_sha256"] is None:
            return False
        return row["content_sha256"] == self.content_sha256(snapshot_id)
