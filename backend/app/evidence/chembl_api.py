import hashlib
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.evidence.retractions import FrozenRetractionIndex
from app.evidence.store import EvidenceStore, EvidenceStoreError, SnapshotSpec, _canonical_json

API_BASE_URI = "https://www.ebi.ac.uk/chembl/api/data"
API_DOCUMENTATION_URI = (
    "https://chembl.gitbook.io/chembl-interface-documentation/"
    "web-services/chembl-data-web-services"
)
MANIFEST_FILENAME = "manifest.json"
MANIFEST_SCHEMA_VERSION = 1


class ChemblApiError(EvidenceStoreError):
    """Raised when a ChEMBL API acquisition or frozen import is invalid."""


@dataclass(frozen=True, slots=True)
class ChemblApiSelection:
    expected_release: str
    molecule_chembl_ids: tuple[str, ...]
    target_chembl_ids: tuple[str, ...]
    endpoints: tuple[str, ...] = ("IC50", "EC50", "Ki", "Kd")

    def __post_init__(self) -> None:
        if not self.expected_release.startswith("ChEMBL_"):
            raise ValueError("expected_release must look like ChEMBL_37")
        suffix = self.expected_release.removeprefix("ChEMBL_")
        if not suffix.isdigit():
            raise ValueError("expected_release must look like ChEMBL_37")
        if not self.molecule_chembl_ids:
            raise ValueError("at least one ChEMBL molecule ID is required")
        if not self.target_chembl_ids:
            raise ValueError("at least one ChEMBL target ID is required")
        if not self.endpoints:
            raise ValueError("at least one activity endpoint is required")
        for label, values in (
            ("molecule IDs", self.molecule_chembl_ids),
            ("target IDs", self.target_chembl_ids),
            ("endpoints", self.endpoints),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"ChEMBL API selection contains duplicate {label}")
        for identifier in (*self.molecule_chembl_ids, *self.target_chembl_ids):
            if not identifier.startswith("CHEMBL") or not identifier[6:].isdigit():
                raise ValueError(f"invalid ChEMBL identifier: {identifier}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "expected_release": self.expected_release,
            "molecule_chembl_ids": list(self.molecule_chembl_ids),
            "target_chembl_ids": list(self.target_chembl_ids),
            "endpoints": list(self.endpoints),
        }


@dataclass(frozen=True, slots=True)
class ChemblApiAcquisition:
    raw_directory: Path
    release: str
    release_date: str
    response_count: int
    source_sha256: str


@dataclass(frozen=True, slots=True)
class ChemblApiFrozenManifest:
    selection: ChemblApiSelection
    release: str
    release_date: str
    retrieved_at: str
    response_count: int
    source_sha256: str


@dataclass(frozen=True, slots=True)
class ChemblApiImportStats:
    molecules: int
    targets: int
    target_components: int
    papers: int
    assays: int
    activities: int


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _record_sha256(payload: object) -> str:
    return _sha256_bytes(_canonical_json(payload).encode("utf-8"))


def _combined_hash(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _read_json_object(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChemblApiError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ChemblApiError(f"{label} must be a JSON object")
    return value


def _default_fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ProvenanceLab-evidence-snapshot/1.0",
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
    raise ChemblApiError(f"ChEMBL API request failed: {url}") from last_error


def _build_url(
    resource: str,
    *,
    identifier: str | None = None,
    parameters: dict[str, str | int] | None = None,
    base_uri: str,
) -> str:
    path = f"{base_uri.rstrip('/')}/{resource}"
    if identifier is not None:
        path = f"{path}/{urllib.parse.quote(identifier, safe='')}"
    path = f"{path}.json"
    if parameters:
        return f"{path}?{urllib.parse.urlencode(sorted(parameters.items()))}"
    return path


def _chunks(values: Iterable[str], size: int) -> Iterable[tuple[str, ...]]:
    chunk: list[str] = []
    for value in values:
        chunk.append(value)
        if len(chunk) == size:
            yield tuple(chunk)
            chunk = []
    if chunk:
        yield tuple(chunk)


class _RawWriter:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.responses: list[dict[str, Any]] = []

    def add(self, *, resource: str, url: str, payload: bytes) -> dict[str, Any]:
        sequence = len(self.responses) + 1
        filename = f"{sequence:05d}-{resource}.json"
        document = _read_json_object(payload, label=f"ChEMBL {resource} response")
        self.directory.joinpath(filename).write_bytes(payload)
        entry = {
            "resource": resource,
            "filename": filename,
            "url": url,
            "sha256": _sha256_bytes(payload),
            "record_count": _response_record_count(resource, document),
        }
        self.responses.append(entry)
        return document


def _response_record_count(resource: str, document: dict[str, Any]) -> int:
    plural = {
        "activity": "activities",
        "assay": "assays",
        "document": "documents",
    }.get(resource)
    if plural is None:
        return 1
    records = document.get(plural)
    if not isinstance(records, list):
        raise ChemblApiError(f"ChEMBL {resource} response has no {plural} array")
    return len(records)


def _next_url(document: dict[str, Any], *, base_uri: str) -> str | None:
    page_meta = document.get("page_meta")
    if not isinstance(page_meta, dict):
        raise ChemblApiError("paginated ChEMBL response has no page_meta object")
    next_path = page_meta.get("next")
    if next_path is None:
        return None
    if not isinstance(next_path, str) or not next_path:
        raise ChemblApiError("paginated ChEMBL response has an invalid next URL")
    parsed = urllib.parse.urlsplit(base_uri)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    resolved = urllib.parse.urljoin(origin, next_path)
    resolved_parts = urllib.parse.urlsplit(resolved)
    if (resolved_parts.scheme, resolved_parts.netloc) != (parsed.scheme, parsed.netloc):
        raise ChemblApiError("ChEMBL pagination attempted to change API origin")
    return resolved


def _collect_list_records(document: dict[str, Any], plural: str) -> list[dict[str, Any]]:
    records = document.get(plural)
    if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
        raise ChemblApiError(f"ChEMBL response has an invalid {plural} array")
    return records


def acquire_chembl_api_snapshot(
    raw_directory: str | Path,
    *,
    selection: ChemblApiSelection,
    retrieved_at: str,
    fetch: Callable[[str], bytes] = _default_fetch,
    base_uri: str = API_BASE_URI,
) -> ChemblApiAcquisition:
    """Fetch a selected API corpus once and persist exact, hashed response bytes."""

    output_path = Path(raw_directory).resolve()
    if output_path.exists():
        raise ChemblApiError(f"refusing to overwrite existing raw snapshot: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = Path(
        tempfile.mkdtemp(prefix=f".{output_path.name}.", dir=output_path.parent)
    )
    try:
        writer = _RawWriter(temporary_path)
        status_url = _build_url("status", base_uri=base_uri)
        status = writer.add(resource="status", url=status_url, payload=fetch(status_url))
        release = status.get("chembl_db_version")
        release_date = status.get("chembl_release_date")
        if status.get("status") != "UP":
            raise ChemblApiError("ChEMBL API status is not UP")
        if release != selection.expected_release:
            raise ChemblApiError(
                f"expected {selection.expected_release}, but the API reports {release!r}"
            )
        if not isinstance(release_date, str) or not release_date:
            raise ChemblApiError("ChEMBL API status has no release date")

        for identifier in sorted(set(selection.molecule_chembl_ids)):
            url = _build_url("molecule", identifier=identifier, base_uri=base_uri)
            writer.add(resource="molecule", url=url, payload=fetch(url))
        for identifier in sorted(set(selection.target_chembl_ids)):
            url = _build_url("target", identifier=identifier, base_uri=base_uri)
            writer.add(resource="target", url=url, payload=fetch(url))

        activity_url = _build_url(
            "activity",
            parameters={
                "limit": 1000,
                "molecule_chembl_id__in": ",".join(selection.molecule_chembl_ids),
                "standard_type__in": ",".join(selection.endpoints),
                "target_chembl_id__in": ",".join(selection.target_chembl_ids),
            },
            base_uri=base_uri,
        )
        activity_records: list[dict[str, Any]] = []
        seen_page_urls: set[str] = set()
        while activity_url is not None:
            if activity_url in seen_page_urls:
                raise ChemblApiError("ChEMBL activity pagination contains a cycle")
            seen_page_urls.add(activity_url)
            page = writer.add(
                resource="activity",
                url=activity_url,
                payload=fetch(activity_url),
            )
            activity_records.extend(_collect_list_records(page, "activities"))
            activity_url = _next_url(page, base_uri=base_uri)

        assay_ids = sorted(
            {
                str(record["assay_chembl_id"])
                for record in activity_records
                if record.get("assay_chembl_id")
            }
        )
        document_ids = sorted(
            {
                str(record["document_chembl_id"])
                for record in activity_records
                if record.get("document_chembl_id")
            }
        )
        for resource, field, identifiers in (
            ("assay", "assay_chembl_id__in", assay_ids),
            ("document", "document_chembl_id__in", document_ids),
        ):
            for identifier_chunk in _chunks(identifiers, 50):
                url = _build_url(
                    resource,
                    parameters={field: ",".join(identifier_chunk), "limit": 1000},
                    base_uri=base_uri,
                )
                page = writer.add(resource=resource, url=url, payload=fetch(url))
                if _next_url(page, base_uri=base_uri) is not None:
                    raise ChemblApiError(
                        f"ChEMBL {resource} batch unexpectedly exceeded 1000 records"
                    )

        manifest_without_hash = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "source": {
                "name": "ChEMBL Data Web Services",
                "base_uri": base_uri,
                "documentation_uri": API_DOCUMENTATION_URI,
                "chembl_db_version": release,
                "chembl_release_date": release_date,
            },
            "selection": selection.as_dict(),
            "retrieved_at": retrieved_at,
            "responses": writer.responses,
        }
        source_sha256 = _record_sha256(manifest_without_hash)
        manifest = {**manifest_without_hash, "source_sha256": source_sha256}
        temporary_path.joinpath(MANIFEST_FILENAME).write_text(
            f"{_canonical_json(manifest)}\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, output_path)
    except BaseException:
        shutil.rmtree(temporary_path, ignore_errors=True)
        raise
    return ChemblApiAcquisition(
        raw_directory=output_path,
        release=str(release),
        release_date=release_date,
        response_count=len(writer.responses),
        source_sha256=source_sha256,
    )


def _load_manifest(raw_directory: str | Path) -> tuple[Path, dict[str, Any]]:
    raw_path = Path(raw_directory).resolve()
    manifest_path = raw_path / MANIFEST_FILENAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ChemblApiError(f"cannot read frozen ChEMBL manifest: {manifest_path}") from error
    if not isinstance(manifest, dict):
        raise ChemblApiError("frozen ChEMBL manifest must be a JSON object")
    source_hash = manifest.get("source_sha256")
    manifest_without_hash = {
        key: value for key, value in manifest.items() if key != "source_sha256"
    }
    if source_hash != _record_sha256(manifest_without_hash):
        raise ChemblApiError("frozen ChEMBL manifest hash does not match its content")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ChemblApiError("unsupported frozen ChEMBL manifest schema")
    responses = manifest.get("responses")
    if not isinstance(responses, list) or not responses:
        raise ChemblApiError("frozen ChEMBL manifest has no responses")
    return raw_path, manifest


def _load_frozen_responses(
    raw_directory: str | Path,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    raw_path, manifest = _load_manifest(raw_directory)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in manifest["responses"]:
        if not isinstance(entry, dict):
            raise ChemblApiError("frozen ChEMBL response entry must be an object")
        filename = entry.get("filename")
        resource = entry.get("resource")
        expected_hash = entry.get("sha256")
        if (
            not isinstance(filename, str)
            or Path(filename).name != filename
            or not isinstance(resource, str)
            or not isinstance(expected_hash, str)
        ):
            raise ChemblApiError("frozen ChEMBL response entry is malformed")
        response_path = raw_path / filename
        try:
            payload = response_path.read_bytes()
        except OSError as error:
            raise ChemblApiError(f"missing frozen ChEMBL response: {filename}") from error
        if _sha256_bytes(payload) != expected_hash:
            raise ChemblApiError(f"frozen ChEMBL response hash mismatch: {filename}")
        document = _read_json_object(payload, label=f"frozen ChEMBL response {filename}")
        if _response_record_count(resource, document) != entry.get("record_count"):
            raise ChemblApiError(f"frozen ChEMBL response count mismatch: {filename}")
        grouped.setdefault(resource, []).append(document)
    return manifest, grouped


def _selection_from_manifest(manifest: dict[str, Any]) -> ChemblApiSelection:
    payload = manifest.get("selection")
    if not isinstance(payload, dict):
        raise ChemblApiError("frozen ChEMBL manifest has no selection object")
    try:
        return ChemblApiSelection(
            expected_release=payload["expected_release"],
            molecule_chembl_ids=tuple(payload["molecule_chembl_ids"]),
            target_chembl_ids=tuple(payload["target_chembl_ids"]),
            endpoints=tuple(payload["endpoints"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ChemblApiError("frozen ChEMBL selection is invalid") from error


def inspect_frozen_chembl_api_snapshot(
    raw_directory: str | Path,
) -> ChemblApiFrozenManifest:
    """Read and hash-check frozen manifest metadata without loading response bodies."""

    _, manifest = _load_manifest(raw_directory)
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ChemblApiError("frozen ChEMBL manifest has no source object")
    release = source.get("chembl_db_version")
    release_date = source.get("chembl_release_date")
    retrieved_at = manifest.get("retrieved_at")
    responses = manifest.get("responses")
    metadata_values = (release, release_date, retrieved_at)
    if not all(isinstance(value, str) and value for value in metadata_values):
        raise ChemblApiError("frozen ChEMBL manifest has incomplete source metadata")
    if not isinstance(responses, list):
        raise ChemblApiError("frozen ChEMBL manifest has no responses")
    return ChemblApiFrozenManifest(
        selection=_selection_from_manifest(manifest),
        release=release,
        release_date=release_date,
        retrieved_at=retrieved_at,
        response_count=len(responses),
        source_sha256=str(manifest["source_sha256"]),
    )


def _records(grouped: dict[str, list[dict[str, Any]]], resource: str) -> list[dict[str, Any]]:
    if resource in {"molecule", "target", "status"}:
        return grouped.get(resource, [])
    plural = {"activity": "activities", "assay": "assays", "document": "documents"}[
        resource
    ]
    return [
        record
        for document in grouped.get(resource, [])
        for record in _collect_list_records(document, plural)
    ]


def _require_exact_ids(
    *, requested: tuple[str, ...], found: set[str], entity: str
) -> None:
    missing = sorted(set(requested) - found)
    extras = sorted(found - set(requested))
    if missing or extras:
        raise ChemblApiError(
            f"frozen ChEMBL {entity} selection mismatch; missing={missing}, extras={extras}"
        )


def _optional_float(value: Any, *, field: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ChemblApiError(f"ChEMBL {field} is not numeric: {value!r}") from error


def _optional_int(value: Any, *, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ChemblApiError(f"ChEMBL {field} is not an integer: {value!r}") from error


def import_chembl_api_snapshot(
    store: EvidenceStore,
    *,
    raw_directory: str | Path,
    snapshot_id: str,
    created_at: str,
    retraction_index: FrozenRetractionIndex,
) -> ChemblApiImportStats:
    """Verify and normalize a frozen API acquisition into a sealed evidence snapshot."""

    manifest, grouped = _load_frozen_responses(raw_directory)
    selection = _selection_from_manifest(manifest)
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ChemblApiError("frozen ChEMBL manifest has no source object")
    release = source.get("chembl_db_version")
    if release != selection.expected_release:
        raise ChemblApiError(
            f"manifest release {release!r} does not match pinned {selection.expected_release}"
        )
    status_records = _records(grouped, "status")
    if len(status_records) != 1 or status_records[0].get("chembl_db_version") != release:
        raise ChemblApiError("frozen ChEMBL status response does not match the manifest")

    molecules = _records(grouped, "molecule")
    targets = _records(grouped, "target")
    activities = _records(grouped, "activity")
    assays = _records(grouped, "assay")
    documents = _records(grouped, "document")
    _require_exact_ids(
        requested=selection.molecule_chembl_ids,
        found={str(row.get("molecule_chembl_id")) for row in molecules},
        entity="molecule",
    )
    _require_exact_ids(
        requested=selection.target_chembl_ids,
        found={str(row.get("target_chembl_id")) for row in targets},
        entity="target",
    )

    molecule_by_id: dict[str, str] = {}
    for row in molecules:
        structures = row.get("molecule_structures")
        if not isinstance(structures, dict):
            raise ChemblApiError(
                f"selected molecule has no structure: {row.get('molecule_chembl_id')}"
            )
        chembl_id = str(row["molecule_chembl_id"])
        inchikey = structures.get("standard_inchi_key")
        smiles = structures.get("canonical_smiles")
        if not isinstance(inchikey, str) or not isinstance(smiles, str):
            raise ChemblApiError(f"selected molecule has no usable structure: {chembl_id}")
        molecule_by_id[chembl_id] = inchikey

    assay_by_id = {
        str(row["assay_chembl_id"]): row
        for row in assays
        if row.get("assay_chembl_id")
    }
    document_by_id = {
        str(row["document_chembl_id"]): row
        for row in documents
        if row.get("document_chembl_id")
    }
    required_assays = {
        str(row["assay_chembl_id"])
        for row in activities
        if row.get("assay_chembl_id")
    }
    required_documents = {
        str(row["document_chembl_id"])
        for row in activities
        if row.get("document_chembl_id")
    }
    if missing_assays := sorted(required_assays - assay_by_id.keys()):
        raise ChemblApiError(f"frozen ChEMBL snapshot is missing assays: {missing_assays}")
    if missing_documents := sorted(required_documents - document_by_id.keys()):
        raise ChemblApiError(f"frozen ChEMBL snapshot is missing documents: {missing_documents}")

    chembl_source_hash = str(manifest["source_sha256"])
    source_hash = _combined_hash(chembl_source_hash, retraction_index.source_sha256)
    with store.batch():
        store.register_snapshot(
            SnapshotSpec(
                snapshot_id=snapshot_id,
                source_name="ChEMBL Data Web Services + frozen retraction screen",
                source_version=str(release),
                source_sha256=source_hash,
                source_uri=str(source.get("documentation_uri") or API_DOCUMENTATION_URI),
                license="CC BY-SA 3.0; retraction metadata CC0",
                scope={
                    **selection.as_dict(),
                    "chembl_api_source_sha256": chembl_source_hash,
                    "retraction_source_sha256": retraction_index.source_sha256,
                    "retrieved_at": manifest.get("retrieved_at"),
                },
                created_at=created_at,
            )
        )

        for row in molecules:
            chembl_id = str(row["molecule_chembl_id"])
            inchikey = molecule_by_id[chembl_id]
            structures = row["molecule_structures"]
            hierarchy = row.get("molecule_hierarchy")
            parent_id = hierarchy.get("parent_chembl_id") if isinstance(hierarchy, dict) else None
            store.add_molecule(
                snapshot_id=snapshot_id,
                inchikey=inchikey,
                canonical_smiles=structures["canonical_smiles"],
                parent_inchikey=molecule_by_id.get(str(parent_id)),
                preferred_name=row.get("pref_name"),
                chembl_id=chembl_id,
                raw_record_sha256=_record_sha256(row),
            )
            aliases: list[tuple[str, str]] = []
            if row.get("pref_name"):
                aliases.append((str(row["pref_name"]), "CHEMBL_API_PREF_NAME"))
            synonyms = row.get("molecule_synonyms") or []
            if not isinstance(synonyms, list):
                raise ChemblApiError(f"invalid molecule synonyms for {chembl_id}")
            for synonym in synonyms:
                if isinstance(synonym, dict) and synonym.get("synonyms"):
                    source_name = f"CHEMBL_API_SYNONYM:{synonym.get('syn_type') or 'UNKNOWN'}"
                    aliases.append((str(synonym["synonyms"]), source_name))
            for alias, alias_source in dict.fromkeys(aliases):
                store.add_molecule_alias(
                    snapshot_id=snapshot_id,
                    inchikey=inchikey,
                    alias=alias,
                    source=alias_source,
                )

        component_count = 0
        for row in targets:
            target_id = str(row["target_chembl_id"])
            components = row.get("target_components") or []
            if not isinstance(components, list):
                raise ChemblApiError(f"invalid target components for {target_id}")
            component_synonyms = [
                synonym
                for component in components
                if isinstance(component, dict)
                for synonym in component.get("target_component_synonyms", [])
                if isinstance(synonym, dict)
            ]
            accessions = sorted(
                {
                    str(component["accession"])
                    for component in components
                    if isinstance(component, dict) and component.get("accession")
                }
            )
            gene_symbols = sorted(
                {
                    str(synonym["component_synonym"])
                    for synonym in component_synonyms
                    if synonym.get("syn_type") == "GENE_SYMBOL"
                    and synonym.get("component_synonym")
                }
            )
            store.add_target(
                snapshot_id=snapshot_id,
                target_id=target_id,
                preferred_name=str(row.get("pref_name") or target_id),
                organism=row.get("organism"),
                target_type=row.get("target_type"),
                accession=accessions[0] if len(accessions) == 1 else None,
                gene_symbol=gene_symbols[0] if len(gene_symbols) == 1 else None,
                raw_record_sha256=_record_sha256(row),
            )
            aliases: list[tuple[str, str]] = []
            if row.get("pref_name"):
                aliases.append((str(row["pref_name"]), "CHEMBL_API_PREF_NAME"))
            for synonym in component_synonyms:
                if synonym.get("component_synonym"):
                    alias_source = (
                        f"CHEMBL_API_COMPONENT:{synonym.get('syn_type') or 'UNKNOWN'}"
                    )
                    aliases.append((str(synonym["component_synonym"]), alias_source))
            for alias, alias_source in dict.fromkeys(aliases):
                store.add_target_alias(
                    snapshot_id=snapshot_id,
                    target_id=target_id,
                    alias=alias,
                    source=alias_source,
                )
            for component in components:
                if not isinstance(component, dict) or component.get("component_id") is None:
                    raise ChemblApiError(f"invalid target component for {target_id}")
                store.add_target_component(
                    snapshot_id=snapshot_id,
                    target_id=target_id,
                    component_id=int(component["component_id"]),
                    accession=component.get("accession"),
                    component_type=component.get("component_type"),
                    description=component.get("component_description"),
                    organism=row.get("organism"),
                    homologue=0,
                    raw_record_sha256=_record_sha256(component),
                )
                component_count += 1

        for document_id in sorted(required_documents):
            row = document_by_id[document_id]
            pmid = str(row["pubmed_id"]) if row.get("pubmed_id") is not None else None
            doi = str(row["doi"]) if row.get("doi") else None
            store.add_paper(
                snapshot_id=snapshot_id,
                paper_id=document_id,
                pmid=pmid,
                doi=doi,
                title=row.get("title"),
                retraction_status=retraction_index.status_for(doi=doi, pmid=pmid).value,
                raw_record_sha256=_record_sha256(row),
            )

        for assay_id in sorted(required_assays):
            row = assay_by_id[assay_id]
            target_id = row.get("target_chembl_id")
            if target_id not in selection.target_chembl_ids:
                raise ChemblApiError(f"assay {assay_id} points outside selected targets")
            document_id = row.get("document_chembl_id")
            store.add_assay(
                snapshot_id=snapshot_id,
                assay_id=assay_id,
                source="CHEMBL",
                target_id=target_id,
                organism=row.get("assay_organism"),
                assay_type=row.get("assay_type"),
                description=row.get("description"),
                conditions={
                    "test_type": row.get("assay_test_type"),
                    "category": row.get("assay_category"),
                    "strain": row.get("assay_strain"),
                    "tissue": row.get("assay_tissue"),
                    "cell_type": row.get("assay_cell_type"),
                    "subcellular_fraction": row.get("assay_subcellular_fraction"),
                    "relationship_type": row.get("relationship_type"),
                    "bao_format": row.get("bao_format"),
                    "assay_group": row.get("assay_group"),
                    "variant_sequence": row.get("variant_sequence"),
                },
                target_confidence_score=_optional_int(
                    row.get("confidence_score"), field="confidence_score"
                ),
                paper_id=str(document_id) if document_id else None,
                raw_record_sha256=_record_sha256(row),
            )

        allowed_molecules = set(selection.molecule_chembl_ids)
        allowed_targets = set(selection.target_chembl_ids)
        allowed_endpoints = set(selection.endpoints)
        for row in activities:
            molecule_id = row.get("molecule_chembl_id")
            target_id = row.get("target_chembl_id")
            endpoint = row.get("standard_type")
            if (
                molecule_id not in allowed_molecules
                or target_id not in allowed_targets
                or endpoint not in allowed_endpoints
            ):
                raise ChemblApiError(
                    f"activity {row.get('activity_id')} falls outside the frozen selection"
                )
            assay_id = str(row.get("assay_chembl_id"))
            if assay_id not in assay_by_id:
                raise ChemblApiError(f"activity has unknown assay: {assay_id}")
            activity_id = row.get("activity_id")
            if activity_id is None:
                raise ChemblApiError("ChEMBL activity has no activity_id")
            store.add_activity(
                snapshot_id=snapshot_id,
                activity_id=str(activity_id),
                assay_id=assay_id,
                molecule_inchikey=molecule_by_id[str(molecule_id)],
                measurement_type=str(endpoint or row.get("type") or "UNKNOWN"),
                original_value=_optional_float(row.get("value"), field="value"),
                original_unit=row.get("units"),
                original_relation=row.get("relation"),
                original_text_value=row.get("text_value"),
                standard_value=_optional_float(
                    row.get("standard_value"), field="standard_value"
                ),
                standard_unit=row.get("standard_units"),
                standard_relation=row.get("standard_relation"),
                standard_text_value=row.get("standard_text_value"),
                pchembl_value=_optional_float(row.get("pchembl_value"), field="pchembl_value"),
                activity_outcome=row.get("activity_comment"),
                data_validity_comment=row.get("data_validity_comment"),
                potential_duplicate=bool(row.get("potential_duplicate") or False),
                raw_record_sha256=_record_sha256(row),
            )
        store.seal_snapshot(snapshot_id)

    if not store.verify_snapshot(snapshot_id):
        raise ChemblApiError("sealed ChEMBL API snapshot failed content verification")
    return ChemblApiImportStats(
        molecules=len(molecules),
        targets=len(targets),
        target_components=component_count,
        papers=len(required_documents),
        assays=len(required_assays),
        activities=len(activities),
    )
