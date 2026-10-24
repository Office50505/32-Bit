import hashlib
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.evidence.chembl_api import (
    API_BASE_URI,
    ChemblApiError,
    ChemblApiSelection,
    acquire_chembl_api_snapshot,
    frozen_chembl_document_identifiers,
    import_chembl_api_snapshot,
    inspect_frozen_chembl_api_snapshot,
)
from app.evidence.retractions import FrozenRetractionIndex
from app.evidence.store import EvidenceStore, EvidenceStoreError
from app.models.evidence_assistant import ClaimDecomposition
from app.services.claim_routing import ClaimRoute, infer_endpoint, route_statement

RETRACTION_WATCH_URL = (
    "https://gitlab.com/crossref/retraction-watch-data/-/raw/main/"
    "retraction_watch.csv?ref_type=heads&inline=false"
)
DEFAULT_ENDPOINTS = ("IC50", "EC50", "Ki", "Kd")


class DynamicChemblError(RuntimeError):
    """Raised when an on-demand ChEMBL evidence snapshot cannot be built safely."""


@dataclass(frozen=True, slots=True)
class ResolvedChemblPair:
    release: str
    molecule_id: str
    target_id: str


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ProvenanceLab-dynamic-evidence/1.0",
        },
    )
    last_error: BaseException | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except (TimeoutError, urllib.error.HTTPError, urllib.error.URLError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2**attempt)
    raise DynamicChemblError(f"ChEMBL request failed: {url}") from last_error


def _json_object(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DynamicChemblError(f"{label} did not return valid JSON") from error
    if not isinstance(value, dict):
        raise DynamicChemblError(f"{label} did not return a JSON object")
    return value


def _url(resource: str, *, query: str | None = None, base_uri: str) -> str:
    path = f"{base_uri.rstrip('/')}/{resource}"
    if query is not None:
        path = f"{path}/search"
    path = f"{path}.json"
    if query is None:
        return path
    return f"{path}?{urllib.parse.urlencode({'limit': 20, 'q': query})}"


def _normalized_mention(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def _molecule_aliases(record: dict[str, Any]) -> set[str]:
    aliases = {
        str(record.get("molecule_chembl_id") or ""),
        str(record.get("pref_name") or ""),
    }
    for synonym in record.get("molecule_synonyms") or []:
        if isinstance(synonym, dict) and synonym.get("synonyms"):
            aliases.add(str(synonym["synonyms"]))
    return {_normalized_mention(alias) for alias in aliases if alias}


def _target_aliases(record: dict[str, Any]) -> set[str]:
    aliases = {
        str(record.get("target_chembl_id") or ""),
        str(record.get("pref_name") or ""),
    }
    for component in record.get("target_components") or []:
        if not isinstance(component, dict):
            continue
        for synonym in component.get("target_component_synonyms") or []:
            if isinstance(synonym, dict) and synonym.get("component_synonym"):
                aliases.add(str(synonym["component_synonym"]))
    return {_normalized_mention(alias) for alias in aliases if alias}


def _records(document: dict[str, Any], plural: str) -> list[dict[str, Any]]:
    records = document.get(plural)
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise DynamicChemblError(f"ChEMBL search response has no valid {plural} array")
    return records


def _choose_molecule(records: list[dict[str, Any]], mention: str) -> str | None:
    normalized = _normalized_mention(mention)
    exact = [row for row in records if normalized in _molecule_aliases(row)]
    identifiers = {
        str(row["molecule_chembl_id"])
        for row in exact
        if row.get("molecule_chembl_id")
    }
    return next(iter(identifiers)) if len(identifiers) == 1 else None


def _target_query_mention(mention: str) -> tuple[str, str | None]:
    normalized = _normalized_mention(mention)
    organism = None
    for prefix, value in (
        ("human ", "Homo sapiens"),
        ("mouse ", "Mus musculus"),
        ("rat ", "Rattus norvegicus"),
    ):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix).strip()
            organism = value
            break
    return normalized, organism


def _choose_target(records: list[dict[str, Any]], mention: str) -> str | None:
    normalized, organism_hint = _target_query_mention(mention)
    exact = [row for row in records if normalized in _target_aliases(row)]
    if organism_hint is not None:
        exact = [row for row in exact if row.get("organism") == organism_hint]
    identifiers = {
        str(row["target_chembl_id"])
        for row in exact
        if row.get("target_chembl_id")
    }
    if len(identifiers) == 1:
        return next(iter(identifiers))

    # Most plain gene-symbol questions intend the curated human single-protein
    # target. Only apply that convention when it selects exactly one record.
    human_single = [
        row
        for row in exact
        if row.get("organism") == "Homo sapiens"
        and row.get("target_type") == "SINGLE PROTEIN"
    ]
    human_ids = {
        str(row["target_chembl_id"])
        for row in human_single
        if row.get("target_chembl_id")
    }
    return next(iter(human_ids)) if len(human_ids) == 1 else None


class DynamicChemblSnapshots:
    """Resolve, freeze, import, and reuse ChEMBL evidence for claim-specific pairs."""

    def __init__(
        self,
        *,
        fixed_database_path: str | Path,
        combined_database_path: str | Path,
        raw_root: str | Path,
        retraction_watch_csv: str | Path,
        base_uri: str = API_BASE_URI,
        fetch: Callable[[str], bytes] = _fetch,
        enabled: bool = True,
    ) -> None:
        self.fixed_database_path = Path(fixed_database_path).resolve()
        self.combined_database_path = Path(combined_database_path).resolve()
        self.raw_root = Path(raw_root).resolve()
        self.retraction_watch_csv = Path(retraction_watch_csv).resolve()
        self.base_uri = base_uri.rstrip("/")
        self.fetch = fetch
        self.enabled = enabled

    def ensure_for_decomposition(
        self,
        decomposition: ClaimDecomposition,
    ) -> tuple[str, ...]:
        if not self.enabled:
            return ()
        snapshot_ids: list[str] = []
        for statement in decomposition.statements:
            if route_statement(statement).route != ClaimRoute.STRUCTURED_ASSAY:
                continue
            if len(statement.molecule_mentions) != 1 or len(statement.target_mentions) != 1:
                continue
            endpoint, endpoint_reasons = infer_endpoint(statement)
            if endpoint_reasons:
                continue
            pair = self._resolve_pair(
                statement.molecule_mentions[0],
                statement.target_mentions[0],
            )
            if pair is None:
                continue
            snapshot_id = self._ensure_pair_snapshot(
                pair,
                endpoints=(endpoint,) if endpoint is not None else DEFAULT_ENDPOINTS,
            )
            if snapshot_id not in snapshot_ids:
                snapshot_ids.append(snapshot_id)
        return tuple(snapshot_ids)

    def _resolve_pair(
        self,
        molecule_mention: str,
        target_mention: str,
    ) -> ResolvedChemblPair | None:
        status_url = _url("status", base_uri=self.base_uri)
        status = _json_object(self.fetch(status_url), label="ChEMBL status")
        release = status.get("chembl_db_version")
        if status.get("status") != "UP" or not isinstance(release, str):
            raise DynamicChemblError("ChEMBL API is unavailable or did not report a release")

        molecule_url = _url(
            "molecule",
            query=molecule_mention,
            base_uri=self.base_uri,
        )
        molecule_document = _json_object(
            self.fetch(molecule_url),
            label="ChEMBL molecule search",
        )
        target_query, _ = _target_query_mention(target_mention)
        target_url = _url("target", query=target_query, base_uri=self.base_uri)
        target_document = _json_object(
            self.fetch(target_url),
            label="ChEMBL target search",
        )
        molecule_id = _choose_molecule(
            _records(molecule_document, "molecules"),
            molecule_mention,
        )
        target_id = _choose_target(
            _records(target_document, "targets"),
            target_mention,
        )
        if molecule_id is None or target_id is None:
            return None
        return ResolvedChemblPair(
            release=release,
            molecule_id=molecule_id,
            target_id=target_id,
        )

    def _ensure_pair_snapshot(
        self,
        pair: ResolvedChemblPair,
        *,
        endpoints: tuple[str, ...],
    ) -> str:
        selection = ChemblApiSelection(
            expected_release=pair.release,
            molecule_chembl_ids=(pair.molecule_id,),
            target_chembl_ids=(pair.target_id,),
            endpoints=endpoints,
        )
        selection_hash = _sha256(selection.as_dict())
        release_number = pair.release.removeprefix("ChEMBL_")
        snapshot_id = (
            f"chembl-api-{release_number}-{pair.molecule_id.casefold()}-"
            f"{pair.target_id.casefold()}-{selection_hash[:12]}"
        )
        raw_directory = self.raw_root / snapshot_id
        retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        try:
            if raw_directory.exists():
                manifest = inspect_frozen_chembl_api_snapshot(raw_directory)
                if manifest.selection != selection:
                    raise DynamicChemblError(
                        f"cached ChEMBL snapshot selection mismatch: {snapshot_id}"
                    )
                created_at = manifest.retrieved_at
            else:
                acquire_chembl_api_snapshot(
                    raw_directory,
                    selection=selection,
                    retrieved_at=retrieved_at,
                    fetch=self.fetch,
                    base_uri=self.base_uri,
                )
                created_at = retrieved_at
            self._ensure_combined_database()
            with EvidenceStore.create(self.combined_database_path) as store:
                if store.snapshot_exists(snapshot_id):
                    if not store.verify_snapshot(snapshot_id):
                        raise DynamicChemblError(
                            f"cached ChEMBL snapshot failed verification: {snapshot_id}"
                        )
                    return snapshot_id
                identifiers = frozen_chembl_document_identifiers(raw_directory)
                retraction_index = FrozenRetractionIndex.from_csv_for_identifiers(
                    self._ensure_retraction_watch_csv(),
                    dois=set(identifiers.dois),
                    pmids=set(identifiers.pmids),
                )
                import_chembl_api_snapshot(
                    store,
                    raw_directory=raw_directory,
                    snapshot_id=snapshot_id,
                    created_at=created_at,
                    retraction_index=retraction_index,
                )
        except (ChemblApiError, EvidenceStoreError, OSError) as error:
            raise DynamicChemblError(str(error)) from error
        return snapshot_id

    def _ensure_combined_database(self) -> None:
        if self.combined_database_path.is_file():
            return
        if not self.fixed_database_path.is_file():
            raise DynamicChemblError(
                "The base frozen evidence database is not configured on this machine."
            )
        self.combined_database_path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.combined_database_path.name}.",
            dir=self.combined_database_path.parent,
        )
        os.close(file_descriptor)
        temporary_path = Path(temporary_name)
        try:
            shutil.copy2(self.fixed_database_path, temporary_path)
            os.replace(temporary_path, self.combined_database_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _ensure_retraction_watch_csv(self) -> Path:
        if self.retraction_watch_csv.is_file():
            return self.retraction_watch_csv
        self.retraction_watch_csv.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".retraction-watch-",
            suffix=".csv",
            dir=self.retraction_watch_csv.parent,
        )
        os.close(file_descriptor)
        temporary_path = Path(temporary_name)
        request = urllib.request.Request(
            RETRACTION_WATCH_URL,
            headers={"User-Agent": "ProvenanceLab-retraction-screen/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                with temporary_path.open("wb") as destination:
                    shutil.copyfileobj(response, destination)
            if temporary_path.stat().st_size == 0:
                raise DynamicChemblError("Retraction Watch download was empty")
            os.replace(temporary_path, self.retraction_watch_csv)
        except (TimeoutError, urllib.error.HTTPError, urllib.error.URLError, OSError) as error:
            raise DynamicChemblError(
                "Could not acquire the frozen Retraction Watch screen."
            ) from error
        finally:
            temporary_path.unlink(missing_ok=True)
        return self.retraction_watch_csv
