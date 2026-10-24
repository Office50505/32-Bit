import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Self

from app.evidence.store import EvidenceStore, EvidenceStoreError, SnapshotSpec
from app.models.evidence_assistant import RetractionStatus

RETRACTION_WATCH_COLUMNS = frozenset(
    {
        "Record ID",
        "RetractionDate",
        "OriginalPaperDOI",
        "OriginalPaperPubMedID",
        "RetractionNature",
        "Reason",
    }
)
_NOTICE_TYPES = {
    "retraction": "RETRACTION",
    "expression of concern": "EXPRESSION_OF_CONCERN",
    "correction": "CORRECTION",
    "reinstatement": "REINSTATEMENT",
}
_STATUS_BY_NOTICE = {
    "RETRACTION": RetractionStatus.RETRACTED,
    "EXPRESSION_OF_CONCERN": RetractionStatus.EXPRESSION_OF_CONCERN,
    "CORRECTION": RetractionStatus.CORRECTED,
    "REINSTATEMENT": RetractionStatus.REINSTATED,
}


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix).strip()
    return normalized or None


def normalize_pmid(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized or set(normalized) == {"0"}:
        return None
    return normalized.lstrip("0") or "0"


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip().split(" ", maxsplit=1)[0]
    for date_format in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, date_format)  # noqa: DTZ007 - ordering only
        except ValueError:
            continue
    return None


@dataclass(frozen=True, slots=True)
class RetractionRecord:
    record_id: str
    doi: str | None
    pmid: str | None
    notice_type: str
    notice_date: str | None
    reason: str | None
    raw_record_sha256: str

    @property
    def status(self) -> RetractionStatus:
        return _STATUS_BY_NOTICE[self.notice_type]


class FrozenRetractionIndex:
    def __init__(
        self,
        records: list[RetractionRecord],
        *,
        source_sha256: str,
    ) -> None:
        self.records = records
        self.source_sha256 = source_sha256
        by_doi: dict[str, list[RetractionRecord]] = defaultdict(list)
        by_pmid: dict[str, list[RetractionRecord]] = defaultdict(list)
        for record in records:
            if record.doi:
                by_doi[record.doi].append(record)
            if record.pmid:
                by_pmid[record.pmid].append(record)
        self._by_doi = dict(by_doi)
        self._by_pmid = dict(by_pmid)

    @classmethod
    def from_csv(cls, path: str | Path) -> Self:
        csv_path = Path(path).resolve()
        if not csv_path.is_file():
            raise EvidenceStoreError(f"Retraction Watch CSV does not exist: {csv_path}")
        records: list[RetractionRecord] = []
        with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            fieldnames = set(reader.fieldnames or [])
            missing = sorted(RETRACTION_WATCH_COLUMNS - fieldnames)
            if missing:
                raise EvidenceStoreError(
                    f"Retraction Watch CSV is missing required columns: {missing}"
                )
            for row in reader:
                nature = (row.get("RetractionNature") or "").strip(" ;").casefold()
                notice_type = _NOTICE_TYPES.get(nature)
                if notice_type is None:
                    continue
                record_id = (row.get("Record ID") or "").strip()
                if not record_id:
                    raise EvidenceStoreError("Retraction Watch row has no Record ID")
                doi = normalize_doi(row.get("OriginalPaperDOI"))
                pmid = normalize_pmid(row.get("OriginalPaperPubMedID"))
                if doi is None and pmid is None:
                    continue
                records.append(
                    RetractionRecord(
                        record_id=record_id,
                        doi=doi,
                        pmid=pmid,
                        notice_type=notice_type,
                        notice_date=(row.get("RetractionDate") or "").strip() or None,
                        reason=(row.get("Reason") or "").strip() or None,
                        raw_record_sha256=_canonical_hash(row),
                    )
                )
        records.sort(key=lambda record: record.record_id)
        return cls(records, source_sha256=_file_sha256(csv_path))

    def matching_records(
        self,
        *,
        doi: str | None = None,
        pmid: str | None = None,
    ) -> list[RetractionRecord]:
        matches: dict[str, RetractionRecord] = {}
        normalized_doi = normalize_doi(doi)
        normalized_pmid = normalize_pmid(pmid)
        if normalized_doi:
            matches.update(
                (record.record_id, record) for record in self._by_doi.get(normalized_doi, [])
            )
        if normalized_pmid:
            matches.update(
                (record.record_id, record) for record in self._by_pmid.get(normalized_pmid, [])
            )
        return sorted(matches.values(), key=lambda record: record.record_id)

    def status_for(
        self,
        *,
        doi: str | None = None,
        pmid: str | None = None,
    ) -> RetractionStatus:
        if normalize_doi(doi) is None and normalize_pmid(pmid) is None:
            return RetractionStatus.UNKNOWN
        records = self.matching_records(doi=doi, pmid=pmid)
        if not records:
            return RetractionStatus.CLEAR
        retractions = [record for record in records if record.notice_type == "RETRACTION"]
        reinstatements = [
            record for record in records if record.notice_type == "REINSTATEMENT"
        ]
        if retractions:
            retraction_dates = [
                date
                for record in retractions
                if (date := _parse_date(record.notice_date)) is not None
            ]
            reinstatement_dates = [
                date
                for record in reinstatements
                if (date := _parse_date(record.notice_date)) is not None
            ]
            latest_retraction = max(retraction_dates, default=None)
            latest_reinstatement = max(reinstatement_dates, default=None)
            if (
                latest_retraction is not None
                and latest_reinstatement is not None
                and latest_reinstatement > latest_retraction
            ):
                return RetractionStatus.REINSTATED
            return RetractionStatus.RETRACTED
        if reinstatements:
            return RetractionStatus.REINSTATED
        if any(record.notice_type == "EXPRESSION_OF_CONCERN" for record in records):
            return RetractionStatus.EXPRESSION_OF_CONCERN
        return RetractionStatus.CORRECTED

    def import_snapshot(
        self,
        store: EvidenceStore,
        *,
        snapshot_id: str,
        source_version: str,
        source_uri: str,
        created_at: str,
    ) -> str:
        store.register_snapshot(
            SnapshotSpec(
                snapshot_id=snapshot_id,
                source_name="Crossref Retraction Watch",
                source_version=source_version,
                source_sha256=self.source_sha256,
                source_uri=source_uri,
                license="CC0",
                scope={"record_count": len(self.records)},
                created_at=created_at,
            )
        )
        for record in self.records:
            store.add_retraction(
                snapshot_id=snapshot_id,
                retraction_id=f"RW:{record.record_id}",
                doi=record.doi,
                pmid=record.pmid,
                notice_type=record.notice_type,
                notice_date=record.notice_date,
                reason=record.reason,
                raw_record_sha256=record.raw_record_sha256,
            )
        return store.seal_snapshot(snapshot_id)
