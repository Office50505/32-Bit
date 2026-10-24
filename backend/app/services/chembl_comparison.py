import hashlib
import json
import logging
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from rdkit import Chem

from app.models.analysis import BioactivityEvidence, ResultStatus

CHEMBL_COMPARISON_SCHEMA = "chembl-molecule-comparison-v1"
DEFAULT_CHEMBL_BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"
FetchTransport = Callable[[str, float], bytes]
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CACHE = _PROJECT_ROOT / "data/runtime/chembl-molecule-snapshots"
logger = logging.getLogger(__name__)


class ChemblComparisonError(RuntimeError):
    """Raised when an exact ChEMBL comparison snapshot cannot be acquired safely."""


@dataclass(frozen=True, slots=True)
class FrozenChemblComparison:
    inchikey: str
    release: str
    molecule_chembl_id: str | None
    preferred_name: str | None
    activity_count: int | None
    source_url: str
    retrieved_at: str
    snapshot_id: str
    snapshot_scope: str
    response_sha256: str


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: bytes | object) -> str:
    payload = value if isinstance(value, bytes) else _canonical_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_object(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChemblComparisonError(f"{label} did not return valid JSON") from error
    if not isinstance(value, dict):
        raise ChemblComparisonError(f"{label} did not return a JSON object")
    return value


class FrozenChemblComparisonClient:
    """Acquire one exact-identity ChEMBL summary, then reuse verified response bytes."""

    def __init__(
        self,
        cache_directory: str | Path,
        *,
        base_url: str = DEFAULT_CHEMBL_BASE_URL,
        timeout_seconds: float = 30.0,
        transport: FetchTransport | None = None,
    ) -> None:
        self.cache_directory = Path(cache_directory).resolve()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._transport = transport or self._fetch

    @staticmethod
    def _fetch(url: str, timeout: float) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "ProvenanceLab/2 ChEMBL-comparison-snapshot",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            raise ChemblComparisonError(f"ChEMBL request failed: {url}") from error

    def get_by_inchikey(self, inchikey: str) -> FrozenChemblComparison:
        normalized = inchikey.upper().strip()
        cache_key = _sha256({"schema": CHEMBL_COMPARISON_SCHEMA, "inchikey": normalized})
        record_directory = self.cache_directory / cache_key
        cached = self._read_cached(record_directory, inchikey=normalized)
        if cached is not None:
            return cached

        status_url = f"{self.base_url}/status.json"
        molecule_url = (
            f"{self.base_url}/molecule.json?"
            + urllib.parse.urlencode(
                {
                    "molecule_structures__standard_inchi_key": normalized,
                    "limit": 2,
                }
            )
        )
        status_raw = self._transport(status_url, self.timeout_seconds)
        molecule_raw = self._transport(molecule_url, self.timeout_seconds)
        status_document = _json_object(status_raw, label="ChEMBL status")
        molecule_document = _json_object(molecule_raw, label="ChEMBL molecule lookup")
        release = status_document.get("chembl_db_version")
        if status_document.get("status") != "UP" or not isinstance(release, str):
            raise ChemblComparisonError("ChEMBL did not report an available database release")

        records = molecule_document.get("molecules")
        if not isinstance(records, list):
            raise ChemblComparisonError("ChEMBL molecule lookup has no molecules array")
        exact = [
            record
            for record in records
            if isinstance(record, dict)
            and isinstance(record.get("molecule_structures"), dict)
            and str(record["molecule_structures"].get("standard_inchi_key") or "").upper()
            == normalized
        ]
        if len(exact) > 1:
            raise ChemblComparisonError("ChEMBL returned multiple records for one exact InChIKey")

        retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        activity_raw: bytes | None = None
        activity_url: str | None = None
        molecule_id: str | None = None
        preferred_name: str | None = None
        activity_count: int | None = None
        if exact:
            record = exact[0]
            raw_molecule_id = record.get("molecule_chembl_id")
            if not isinstance(raw_molecule_id, str) or not raw_molecule_id:
                raise ChemblComparisonError("Exact ChEMBL molecule has no stable identifier")
            molecule_id = raw_molecule_id
            raw_preferred_name = record.get("pref_name")
            preferred_name = raw_preferred_name if isinstance(raw_preferred_name, str) else None
            activity_url = (
                f"{self.base_url}/activity.json?"
                + urllib.parse.urlencode(
                    {"molecule_chembl_id": molecule_id, "limit": 1}
                )
            )
            activity_raw = self._transport(activity_url, self.timeout_seconds)
            activity_document = _json_object(activity_raw, label="ChEMBL activity lookup")
            page_meta = activity_document.get("page_meta")
            total_count = page_meta.get("total_count") if isinstance(page_meta, dict) else None
            if not isinstance(total_count, int) or total_count < 0:
                raise ChemblComparisonError("ChEMBL activity lookup has no valid total count")
            activity_count = total_count

        source_hashes = {
            "status": _sha256(status_raw),
            "molecule": _sha256(molecule_raw),
            "activity": _sha256(activity_raw) if activity_raw is not None else None,
        }
        snapshot_hash = _sha256(
            {
                "schema": CHEMBL_COMPARISON_SCHEMA,
                "inchikey": normalized,
                "release": release,
                "molecule_chembl_id": molecule_id,
                "activity_count": activity_count,
                "source_hashes": source_hashes,
            }
        )
        release_label = release.removeprefix("ChEMBL_")
        snapshot_id = (
            f"chembl-{release_label}-{(molecule_id or 'no-match').casefold()}@"
            f"{snapshot_hash[:12]}"
        )
        snapshot_scope = (
            f"Frozen {release} exact-InChIKey molecule record {molecule_id} with "
            f"{activity_count} linked activity records."
            if molecule_id is not None
            else f"Frozen {release} exact-InChIKey lookup returned no molecule record."
        )
        manifest = {
            "schema": CHEMBL_COMPARISON_SCHEMA,
            "inchikey": normalized,
            "release": release,
            "molecule_chembl_id": molecule_id,
            "preferred_name": preferred_name,
            "activity_count": activity_count,
            "source_url": activity_url or molecule_url,
            "retrieved_at": retrieved_at,
            "snapshot_id": snapshot_id,
            "snapshot_scope": snapshot_scope,
            "response_sha256": snapshot_hash,
            "sources": {
                "status": {"url": status_url, "sha256": source_hashes["status"]},
                "molecule": {"url": molecule_url, "sha256": source_hashes["molecule"]},
                "activity": (
                    {"url": activity_url, "sha256": source_hashes["activity"]}
                    if activity_url is not None
                    else None
                ),
            },
        }
        self._write_snapshot(
            record_directory,
            manifest=manifest,
            status_raw=status_raw,
            molecule_raw=molecule_raw,
            activity_raw=activity_raw,
        )
        return self._from_manifest(manifest)

    def _read_cached(
        self,
        record_directory: Path,
        *,
        inchikey: str,
    ) -> FrozenChemblComparison | None:
        manifest_path = record_directory / "manifest.json"
        if not manifest_path.is_file():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ChemblComparisonError("Cached ChEMBL manifest is unreadable") from error
        if manifest.get("schema") != CHEMBL_COMPARISON_SCHEMA:
            raise ChemblComparisonError("Cached ChEMBL snapshot schema does not match")
        if manifest.get("inchikey") != inchikey:
            raise ChemblComparisonError("Cached ChEMBL snapshot identity does not match")
        sources = manifest.get("sources")
        if not isinstance(sources, dict):
            raise ChemblComparisonError("Cached ChEMBL manifest has no source records")
        for name in ("status", "molecule", "activity"):
            source = sources.get(name)
            if source is None:
                continue
            if not isinstance(source, dict) or not isinstance(source.get("sha256"), str):
                raise ChemblComparisonError("Cached ChEMBL source metadata is invalid")
            raw_path = record_directory / f"{name}.json"
            if not raw_path.is_file() or _sha256(raw_path.read_bytes()) != source["sha256"]:
                raise ChemblComparisonError("Cached ChEMBL response checksum does not match")
        return self._from_manifest(manifest)

    @staticmethod
    def _from_manifest(manifest: dict[str, Any]) -> FrozenChemblComparison:
        return FrozenChemblComparison(
            inchikey=str(manifest["inchikey"]),
            release=str(manifest["release"]),
            molecule_chembl_id=manifest.get("molecule_chembl_id"),
            preferred_name=manifest.get("preferred_name"),
            activity_count=manifest.get("activity_count"),
            source_url=str(manifest["source_url"]),
            retrieved_at=str(manifest["retrieved_at"]),
            snapshot_id=str(manifest["snapshot_id"]),
            snapshot_scope=str(manifest["snapshot_scope"]),
            response_sha256=str(manifest["response_sha256"]),
        )

    @staticmethod
    def _write_snapshot(
        record_directory: Path,
        *,
        manifest: dict[str, Any],
        status_raw: bytes,
        molecule_raw: bytes,
        activity_raw: bytes | None,
    ) -> None:
        record_directory.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".{record_directory.name}-",
            dir=record_directory.parent,
        ) as temporary:
            temporary_path = Path(temporary)
            (temporary_path / "status.json").write_bytes(status_raw)
            (temporary_path / "molecule.json").write_bytes(molecule_raw)
            if activity_raw is not None:
                (temporary_path / "activity.json").write_bytes(activity_raw)
            (temporary_path / "manifest.json").write_text(
                _canonical_json(manifest) + "\n",
                encoding="utf-8",
            )
            try:
                temporary_path.replace(record_directory)
            except OSError as error:
                if record_directory.is_dir():
                    # A concurrent request won the immutable-cache race.
                    return
                raise ChemblComparisonError(
                    "The ChEMBL snapshot could not be committed to the local cache"
                ) from error


def _enabled() -> bool:
    raw = os.environ.get("PROVENANCELAB_DYNAMIC_CHEMBL", "1")
    return raw.casefold().strip() not in {"0", "false", "no", "off"}


@lru_cache(maxsize=1)
def _client() -> FrozenChemblComparisonClient:
    return FrozenChemblComparisonClient(
        os.environ.get("PROVENANCELAB_CHEMBL_COMPARISON_CACHE", str(_DEFAULT_CACHE)),
        base_url=os.environ.get("PROVENANCELAB_CHEMBL_URL", DEFAULT_CHEMBL_BASE_URL),
    )


def resolve_bioactivity_evidence(
    standardized_smiles: str,
    *,
    client: FrozenChemblComparisonClient | None = None,
    enabled: bool | None = None,
) -> BioactivityEvidence:
    if enabled is None:
        enabled = _enabled()
    if not enabled:
        return BioactivityEvidence(
            status=ResultStatus.NOT_AVAILABLE,
            snapshot_id="chembl-comparison-disabled",
            snapshot_scope="Dynamic ChEMBL molecule comparison is disabled for this run.",
            reason_code="CHEMBL_COMPARISON_DISABLED",
            reason="No ChEMBL molecule lookup was attempted because the feature is disabled.",
        )
    molecule = Chem.MolFromSmiles(standardized_smiles)
    inchikey = Chem.MolToInchiKey(molecule) if molecule is not None else ""
    if not inchikey:
        return BioactivityEvidence(
            status=ResultStatus.NOT_APPLICABLE,
            snapshot_id="chembl-lookup-not-applicable",
            snapshot_scope="No ChEMBL identifier could be derived from the standardized graph.",
            reason_code="CHEMBL_IDENTIFIER_UNAVAILABLE",
            reason="The standardized structure could not be converted to an InChIKey.",
        )
    try:
        record = (client or _client()).get_by_inchikey(inchikey)
    except Exception:
        # ChEMBL is optional comparison evidence. External/network/cache failure must
        # never discard a valid local RDKit result or a separate PubChem snapshot.
        logger.exception("ChEMBL molecule comparison acquisition failed")
        return BioactivityEvidence(
            status=ResultStatus.NOT_AVAILABLE,
            snapshot_id="chembl-api-unavailable",
            snapshot_scope="ChEMBL acquisition failed; RDKit and PubChem results remain available.",
            reason_code="CHEMBL_SNAPSHOT_ACQUISITION_FAILED",
            reason="The ChEMBL comparison record could not be acquired or checksum-verified.",
        )
    if record.molecule_chembl_id is None:
        return BioactivityEvidence(
            status=ResultStatus.NO_REFERENCE_MATCH,
            release=record.release,
            snapshot_id=record.snapshot_id,
            snapshot_scope=record.snapshot_scope,
            retrieved_at=record.retrieved_at,
            source_url=record.source_url,
            response_sha256=record.response_sha256,
            reason_code="CHEMBL_NO_EXACT_INCHIKEY_MATCH",
            reason="No ChEMBL molecule matches this exact standardized InChIKey.",
        )
    return BioactivityEvidence(
        status=ResultStatus.AVAILABLE,
        molecule_chembl_id=record.molecule_chembl_id,
        preferred_name=record.preferred_name,
        release=record.release,
        activity_count=record.activity_count,
        snapshot_id=record.snapshot_id,
        snapshot_scope=record.snapshot_scope,
        retrieved_at=record.retrieved_at,
        source_url=record.source_url,
        response_sha256=record.response_sha256,
        reason_code="FROZEN_CHEMBL_MOLECULE_ACTIVITY_SUMMARY",
        reason=(
            f"Exact ChEMBL molecule {record.molecule_chembl_id} has "
            f"{record.activity_count} linked activity records in {record.release}."
        ),
    )
