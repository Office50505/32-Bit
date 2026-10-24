import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from app.models.evidence_assistant import (
    RESEARCH_AID_NOTICE,
    AtomicStatement,
    ClaimCheckRequest,
    ClaimCheckResponse,
    ClaimType,
    EvidenceAssistantManifest,
    EvidenceBasis,
    EvidenceDirectness,
    EvidenceItem,
    EvidencePacket,
    EvidenceSourceType,
    EvidenceStance,
    ResolutionStatus,
    ResolutionSummary,
    RetractionStatus,
    Verdict,
    VerdictProposal,
)
from app.services.verdict_engine import materialize_statement_verdict

PUBCHEM_QUESTION_PIPELINE_VERSION = "pubchem-question-snapshot-v1"
PUBCHEM_PROPERTY_FIELDS = (
    "Title,IUPACName,ConnectivitySMILES,SMILES,InChIKey,MolecularFormula,"
    "MolecularWeight,ExactMass,XLogP,TPSA,HBondDonorCount,"
    "HBondAcceptorCount,RotatableBondCount"
)
FetchTransport = Callable[[str, float], bytes]
_CACHE_WRITE_LOCK = Lock()


class PubChemQuestionError(RuntimeError):
    """Raised when a recognized molecule question cannot acquire a frozen record."""


class PubChemCompoundNotFoundError(PubChemQuestionError):
    """Raised when PubChem has no CID for the requested molecular identity."""


@dataclass(frozen=True, slots=True)
class ParsedMoleculeQuestion:
    kind: Literal[
        "compare",
        "describe",
        "formula",
        "weight",
        "exact_mass",
        "logp",
        "tpsa",
        "hbd",
        "hba",
        "rotatable_bonds",
    ]
    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedMoleculeAssertion:
    kind: Literal[
        "formula",
        "same_formula",
        "different_formula",
        "same_inchikey",
        "different_inchikey",
    ]
    names: tuple[str, ...]
    asserted_value: str | None = None


@dataclass(frozen=True, slots=True)
class FrozenPubChemCompound:
    query: str
    cid: int
    title: str
    iupac_name: str | None
    connectivity_smiles: str | None
    isomeric_smiles: str | None
    inchikey: str
    molecular_formula: str | None
    molecular_weight: str | None
    exact_mass: str | None
    xlogp: float | None
    tpsa: float | None
    hbond_donor_count: int | None
    hbond_acceptor_count: int | None
    rotatable_bond_count: int | None
    source_url: str
    retrieved_at: str
    raw_sha256: str

    @property
    def snapshot_id(self) -> str:
        return f"pubchem-pug-cid-{self.cid}@{self.raw_sha256[:12]}"


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


def _trim_question(value: str) -> str:
    return re.sub(r"[?.!\s]+$", "", value.strip())


def _stereo_name(letter: str, base: str) -> str:
    return f"{letter.upper()}-{_trim_question(base)}"


def _normalize_comparison_names(left: str, right: str) -> tuple[str, str]:
    left = _trim_question(left)
    right = _trim_question(right)
    left_suffix = re.fullmatch(r"(.+?)\s+([ld])", left, re.IGNORECASE)
    right_suffix = re.fullmatch(r"(.+?)\s+([ld])", right, re.IGNORECASE)
    left_prefix = re.fullmatch(r"([ld])(?:-|\s+)(.+)", left, re.IGNORECASE)
    right_prefix = re.fullmatch(r"([ld])(?:-|\s+)(.+)", right, re.IGNORECASE)
    if left_suffix and right.casefold() in {"l", "d"}:
        return (
            _stereo_name(left_suffix.group(2), left_suffix.group(1)),
            _stereo_name(right, left_suffix.group(1)),
        )
    if left.casefold() in {"l", "d"} and right_prefix:
        return (
            _stereo_name(left, right_prefix.group(2)),
            _stereo_name(right_prefix.group(1), right_prefix.group(2)),
        )
    matching_suffixes = (
        left_suffix
        and right_suffix
        and left_suffix.group(1).casefold() == right_suffix.group(1).casefold()
    )
    if matching_suffixes and left_suffix and right_suffix:
        return (
            _stereo_name(left_suffix.group(2), left_suffix.group(1)),
            _stereo_name(right_suffix.group(2), right_suffix.group(1)),
        )
    return (
        _stereo_name(left_prefix.group(1), left_prefix.group(2)) if left_prefix else left,
        _stereo_name(right_prefix.group(1), right_prefix.group(2)) if right_prefix else right,
    )


def parse_molecule_question(question: str) -> ParsedMoleculeQuestion | None:
    text = _trim_question(question)
    comparison = re.fullmatch(
        r"(?:what\s+is\s+the\s+)?difference\s+between\s+(.+?)\s+and\s+(.+)",
        text,
        re.IGNORECASE,
    ) or re.fullmatch(r"compare\s+(.+?)\s+and\s+(.+)", text, re.IGNORECASE)
    if comparison:
        names = _normalize_comparison_names(comparison.group(1), comparison.group(2))
        if all(1 < len(name) <= 120 for name in names):
            return ParsedMoleculeQuestion(kind="compare", names=names)

    property_question = re.fullmatch(
        r"(?:what\s+is\s+the\s+)?(molecular\s+formula|molecular\s+weight|"
        r"exact\s+mass|logp|topological\s+polar\s+surface\s+area|tpsa|"
        r"hydrogen[- ]bond\s+donors?|hydrogen[- ]bond\s+acceptors?|"
        r"rotatable\s+bonds?)\s+of\s+(.+)",
        text,
        re.IGNORECASE,
    )
    if property_question:
        property_name = property_question.group(1).casefold()
        if "formula" in property_name:
            kind = "formula"
        elif "weight" in property_name:
            kind = "weight"
        elif "exact" in property_name:
            kind = "exact_mass"
        elif property_name == "logp":
            kind = "logp"
        elif "surface" in property_name or property_name == "tpsa":
            kind = "tpsa"
        elif "donor" in property_name:
            kind = "hbd"
        elif "acceptor" in property_name:
            kind = "hba"
        else:
            kind = "rotatable_bonds"
        name = _trim_question(property_question.group(2))
        if 1 < len(name) <= 120:
            return ParsedMoleculeQuestion(kind=kind, names=(name,))

    description = re.fullmatch(
        r"(?:what\s+is|tell\s+me\s+about|describe|give\s+me\s+(?:facts|information)\s+about)"
        r"\s+([A-Za-z0-9][A-Za-z0-9 +(),.'-]{0,119})",
        text,
        re.IGNORECASE,
    )
    if description:
        name = _trim_question(description.group(1))
        return ParsedMoleculeQuestion(kind="describe", names=(name,))
    return None


def parse_molecule_assertion(claim: str) -> ParsedMoleculeAssertion | None:
    """Parse narrow structured-property assertions without guessing free-form chemistry."""

    text = _trim_question(claim)
    formula = re.fullmatch(
        r"the\s+molecular\s+formula\s+of\s+(.+?)\s+is\s+([A-Z][A-Za-z0-9]*)",
        text,
        re.IGNORECASE,
    )
    if formula:
        name = _trim_question(formula.group(1))
        if 1 < len(name) <= 120:
            return ParsedMoleculeAssertion(
                kind="formula",
                names=(name,),
                asserted_value=formula.group(2),
            )

    comparison = re.fullmatch(
        r"(.+?)\s+and\s+(.+?)\s+have\s+(?:the\s+)?"
        r"(same|different)\s+(molecular\s+formulas?|inchikeys?)",
        text,
        re.IGNORECASE,
    )
    if comparison:
        names = _normalize_comparison_names(comparison.group(1), comparison.group(2))
        if not all(1 < len(name) <= 120 for name in names):
            return None
        relationship = comparison.group(3).casefold()
        property_name = comparison.group(4).casefold()
        property_key = "formula" if "formula" in property_name else "inchikey"
        if property_key == "formula":
            kind = "same_formula" if relationship == "same" else "different_formula"
        else:
            kind = "same_inchikey" if relationship == "same" else "different_inchikey"
        return ParsedMoleculeAssertion(
            kind=kind,
            names=names,
        )
    return None


class FrozenPubChemClient:
    """Fetch once from PUG REST, then reuse a hash-verified immutable local record."""

    def __init__(
        self,
        cache_directory: str | Path,
        *,
        fallback_directories: tuple[str | Path, ...] = (),
        base_url: str = "https://pubchem.ncbi.nlm.nih.gov/rest/pug",
        timeout_seconds: float = 30.0,
        transport: FetchTransport | None = None,
    ) -> None:
        self.cache_directory = Path(cache_directory).resolve()
        self.fallback_directories = tuple(
            Path(directory).resolve() for directory in fallback_directories
        )
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._transport = transport or self._fetch

    @staticmethod
    def _fetch(url: str, timeout: float) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "ProvenanceLab/2 molecule-evidence-snapshot"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise PubChemCompoundNotFoundError(
                    "PubChem has no CID for the requested molecular identity"
                ) from error
            raise PubChemQuestionError("PubChem compound acquisition failed") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise PubChemQuestionError("PubChem compound acquisition failed") from error

    def get(self, name: str) -> FrozenPubChemCompound:
        return self._get("name", name)

    def get_by_inchikey(self, inchikey: str) -> FrozenPubChemCompound:
        return self._get("inchikey", inchikey.upper().strip())

    def _get(
        self,
        namespace: Literal["name", "inchikey"],
        identifier: str,
    ) -> FrozenPubChemCompound:
        normalized = identifier.casefold().strip()
        cache_key = _sha256(
            {
                "namespace": namespace,
                "query": normalized,
                "fields": PUBCHEM_PROPERTY_FIELDS,
            }
        )
        record_directory = self.cache_directory / cache_key
        cached = self._read_cached(record_directory, identifier=identifier)
        if cached is not None:
            return cached
        for directory in (self.cache_directory, *self.fallback_directories):
            matching = self._find_matching_record(
                directory,
                namespace=namespace,
                identifier=identifier,
            )
            if matching is not None:
                return matching

        encoded_identifier = urllib.parse.quote(identifier, safe="")
        url = (
            f"{self.base_url}/compound/{namespace}/{encoded_identifier}/property/"
            f"{PUBCHEM_PROPERTY_FIELDS}/JSON"
        )
        raw = self._transport(url, self.timeout_seconds)
        retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        preliminary = {
            "namespace": namespace,
            "query": identifier,
            "normalized_query": normalized,
            "property_fields": PUBCHEM_PROPERTY_FIELDS,
            "source_url": url,
            "retrieved_at": retrieved_at,
            "raw_sha256": _sha256(raw),
        }
        record = self._parse(raw, name=identifier, manifest=preliminary)
        manifest = {
            **preliminary,
            "cid": record.cid,
            "title": record.title,
            "inchikey": record.inchikey,
        }
        with _CACHE_WRITE_LOCK:
            cached = self._read_cached(record_directory, identifier=identifier)
            if cached is not None:
                return cached
            record_directory.mkdir(parents=True, exist_ok=True)
            self._write_atomic(record_directory / "response.json", raw)
            self._write_atomic(
                record_directory / "manifest.json",
                (_canonical_json(manifest) + "\n").encode("utf-8"),
            )
        return record

    def _read_cached(
        self,
        record_directory: Path,
        *,
        identifier: str,
    ) -> FrozenPubChemCompound | None:
        raw_path = record_directory / "response.json"
        manifest_path = record_directory / "manifest.json"
        if not raw_path.is_file() or not manifest_path.is_file():
            return None
        raw = raw_path.read_bytes()
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PubChemQuestionError("cached PubChem manifest is invalid") from error
        if manifest.get("raw_sha256") != _sha256(raw):
            raise PubChemQuestionError("cached PubChem response failed checksum verification")
        return self._parse(raw, name=identifier, manifest=manifest)

    def _find_matching_record(
        self,
        directory: Path,
        *,
        namespace: Literal["name", "inchikey"],
        identifier: str,
    ) -> FrozenPubChemCompound | None:
        if not directory.is_dir():
            return None
        normalized = identifier.casefold().strip()
        for manifest_path in directory.glob("*/manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if manifest.get("property_fields") != PUBCHEM_PROPERTY_FIELDS:
                continue
            matches = (
                str(manifest.get("inchikey", "")).upper() == identifier.upper()
                if namespace == "inchikey"
                else manifest.get("normalized_query") == normalized
            )
            if not matches:
                continue
            return self._read_cached(manifest_path.parent, identifier=identifier)
        return None

    @staticmethod
    def _write_atomic(path: Path, payload: bytes) -> None:
        temporary = tempfile.NamedTemporaryFile(
            prefix=f".{path.name}.",
            dir=path.parent,
            delete=False,
        )
        temporary_path = Path(temporary.name)
        try:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary.close()
            os.replace(temporary_path, path)
        except BaseException:
            temporary.close()
            temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _parse(
        raw: bytes,
        *,
        name: str,
        manifest: dict[str, Any],
    ) -> FrozenPubChemCompound:
        try:
            payload = json.loads(raw)
            properties = payload["PropertyTable"]["Properties"]
            item = properties[0]
            cid = int(item["CID"])
            inchikey = str(item["InChIKey"])
            title = str(item.get("Title") or name)
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as error:
            raise PubChemQuestionError("PubChem returned an invalid compound record") from error
        if len(properties) != 1:
            raise PubChemQuestionError(f"PubChem name is ambiguous: {name}")
        return FrozenPubChemCompound(
            query=name,
            cid=cid,
            title=title,
            iupac_name=item.get("IUPACName"),
            connectivity_smiles=item.get("ConnectivitySMILES") or item.get("CanonicalSMILES"),
            isomeric_smiles=item.get("SMILES") or item.get("IsomericSMILES"),
            inchikey=inchikey,
            molecular_formula=item.get("MolecularFormula"),
            molecular_weight=item.get("MolecularWeight"),
            exact_mass=item.get("ExactMass"),
            xlogp=float(item["XLogP"]) if item.get("XLogP") is not None else None,
            tpsa=float(item["TPSA"]) if item.get("TPSA") is not None else None,
            hbond_donor_count=(
                int(item["HBondDonorCount"])
                if item.get("HBondDonorCount") is not None
                else None
            ),
            hbond_acceptor_count=(
                int(item["HBondAcceptorCount"])
                if item.get("HBondAcceptorCount") is not None
                else None
            ),
            rotatable_bond_count=(
                int(item["RotatableBondCount"])
                if item.get("RotatableBondCount") is not None
                else None
            ),
            source_url=str(manifest["source_url"]),
            retrieved_at=str(manifest["retrieved_at"]),
            raw_sha256=str(manifest["raw_sha256"]),
        )


class PubChemQuestionAssistant:
    def __init__(self, client: FrozenPubChemClient) -> None:
        self._client = client

    def try_check(self, request: ClaimCheckRequest) -> ClaimCheckResponse | None:
        parsed = parse_molecule_question(request.claim)
        if parsed is None:
            assertion = parse_molecule_assertion(request.claim)
            return self._check_assertion(request, assertion) if assertion else None
        records = tuple(self._client.get(name) for name in parsed.names)
        evidence = [self._evidence(record) for record in records]
        statement = AtomicStatement(
            statement_id="S1",
            text=request.claim.strip(),
            claim_type=ClaimType.COMPUTED_PROPERTY,
            molecule_mentions=[record.title for record in records],
        )
        packet = EvidencePacket(
            statement=statement,
            resolution=ResolutionSummary(status=ResolutionStatus.NOT_REQUIRED),
            evidence_items=evidence,
        )
        proposal = VerdictProposal(
            statement_id="S1",
            verdict=Verdict.SUPPORTED,
            citation_ids=[item.evidence_id for item in evidence],
            reason=self._answer(parsed.kind, records),
            limitations=[
                "The answer is limited to structured PubChem identity and property records."
            ],
        )
        verdict = materialize_statement_verdict(packet, proposal)
        input_hash = _sha256(request.model_dump(mode="json"))
        configuration_hash = _sha256(
            {
                "pipeline_version": PUBCHEM_QUESTION_PIPELINE_VERSION,
                "source_records": [record.raw_sha256 for record in records],
            }
        )
        output_payload = {
            "verdicts": [verdict.model_dump(mode="json")],
            "research_aid_notice": RESEARCH_AID_NOTICE,
        }
        output_hash = _sha256(output_payload)
        pipeline_digest = _sha256(PUBCHEM_QUESTION_PIPELINE_VERSION.encode("utf-8"))
        return ClaimCheckResponse(
            assistant_run_id=f"EA-{input_hash[:12]}-{output_hash[:12]}",
            verdicts=[verdict],
            manifest=EvidenceAssistantManifest(
                model_name="deterministic-pubchem-structure-v1",
                model_digest=pipeline_digest,
                evidence_snapshot_id="+".join(record.snapshot_id for record in records),
                input_sha256=input_hash,
                configuration_sha256=configuration_hash,
                output_sha256=output_hash,
            ),
        )

    def _check_assertion(
        self,
        request: ClaimCheckRequest,
        parsed: ParsedMoleculeAssertion,
    ) -> ClaimCheckResponse:
        records = tuple(self._client.get(name) for name in parsed.names)
        if parsed.kind == "formula":
            property_name = "MolecularFormula"
            observed = records[0].molecular_formula
            agrees = observed == parsed.asserted_value
            reason = (
                f"The frozen PubChem record reports {records[0].title}'s molecular formula "
                f"as {observed}, {'matching' if agrees else 'not matching'} "
                f"the asserted {parsed.asserted_value}."
            )
            claim_type = ClaimType.COMPUTED_PROPERTY
        else:
            property_name = "MolecularFormula" if "formula" in parsed.kind else "InChIKey"
            values = (
                (records[0].molecular_formula, records[1].molecular_formula)
                if property_name == "MolecularFormula"
                else (records[0].inchikey, records[1].inchikey)
            )
            observed_same = values[0] == values[1]
            asserts_same = parsed.kind.startswith("same_")
            agrees = observed_same == asserts_same
            relation = "the same" if observed_same else "different"
            reason = (
                f"The frozen PubChem records report {relation} {property_name} values for "
                f"{records[0].title} and {records[1].title}."
            )
            claim_type = ClaimType.LITERATURE_FACT

        stance = EvidenceStance.SUPPORTS if agrees else EvidenceStance.CONTRADICTS
        evidence = [
            self._evidence(record, property_name=property_name, stance=stance)
            for record in records
        ]
        statement = AtomicStatement(
            statement_id="S1",
            text=request.claim.strip(),
            claim_type=claim_type,
            molecule_mentions=[record.title for record in records],
        )
        packet = EvidencePacket(
            statement=statement,
            resolution=ResolutionSummary(status=ResolutionStatus.NOT_REQUIRED),
            evidence_items=evidence,
        )
        proposal = VerdictProposal(
            statement_id="S1",
            verdict=Verdict.SUPPORTED if agrees else Verdict.CONTRADICTED,
            citation_ids=[item.evidence_id for item in evidence],
            reason=reason,
            limitations=[
                "The verdict is limited to checksum-verified PubChem compound records."
            ],
        )
        verdict = materialize_statement_verdict(packet, proposal)
        input_hash = _sha256(request.model_dump(mode="json"))
        configuration_hash = _sha256(
            {
                "pipeline_version": PUBCHEM_QUESTION_PIPELINE_VERSION,
                "source_records": [record.raw_sha256 for record in records],
                "property": property_name,
            }
        )
        output_payload = {
            "verdicts": [verdict.model_dump(mode="json")],
            "research_aid_notice": RESEARCH_AID_NOTICE,
        }
        output_hash = _sha256(output_payload)
        pipeline_digest = _sha256(PUBCHEM_QUESTION_PIPELINE_VERSION.encode("utf-8"))
        return ClaimCheckResponse(
            assistant_run_id=f"EA-{input_hash[:12]}-{output_hash[:12]}",
            verdicts=[verdict],
            manifest=EvidenceAssistantManifest(
                model_name="deterministic-pubchem-structure-v1",
                model_digest=pipeline_digest,
                evidence_snapshot_id="+".join(record.snapshot_id for record in records),
                input_sha256=input_hash,
                configuration_sha256=configuration_hash,
                output_sha256=output_hash,
            ),
        )

    @staticmethod
    def _evidence(
        record: FrozenPubChemCompound,
        *,
        property_name: str | None = None,
        stance: EvidenceStance = EvidenceStance.SUPPORTS,
    ) -> EvidenceItem:
        evidence_suffix = (
            f"PROPERTY:{property_name}" if property_name else f"RUN:PUBCHEM:CID:{record.cid}"
        )
        return EvidenceItem(
            evidence_id=f"{record.snapshot_id}:{evidence_suffix}",
            source_type=EvidenceSourceType.RUN_RECORD,
            source_record_id=f"PUBCHEM:CID:{record.cid}",
            basis=EvidenceBasis.COMPUTED,
            stance=stance,
            directness=EvidenceDirectness.DIRECT,
            molecule_inchikey=record.inchikey,
            endpoint=property_name or "compound_identity",
            assay_conditions={
                "record_kind": "PUBCHEM_COMPOUND",
                "cid": record.cid,
                "title": record.title,
                "iupac_name": record.iupac_name,
                "molecular_formula": record.molecular_formula,
                "molecular_weight": record.molecular_weight,
                "exact_mass": record.exact_mass,
                "xlogp": record.xlogp,
                "tpsa": record.tpsa,
                "hbond_donor_count": record.hbond_donor_count,
                "hbond_acceptor_count": record.hbond_acceptor_count,
                "rotatable_bond_count": record.rotatable_bond_count,
                "connectivity_smiles": record.connectivity_smiles,
                "isomeric_smiles": record.isomeric_smiles,
                "source_url": record.source_url,
                "retrieved_at": record.retrieved_at,
            },
            retraction_status=RetractionStatus.UNKNOWN,
            snapshot_id=record.snapshot_id,
            raw_record_sha256=record.raw_sha256,
            quality_flags=["STRUCTURED_PUBCHEM_RECORD", "RETRACTION_NOT_APPLICABLE"],
        )

    @staticmethod
    def _answer(
        kind: Literal[
            "compare",
            "describe",
            "formula",
            "weight",
            "exact_mass",
            "logp",
            "tpsa",
            "hbd",
            "hba",
            "rotatable_bonds",
        ],
        records: tuple[FrozenPubChemCompound, ...],
    ) -> str:
        first = records[0]
        if kind == "formula":
            return (
                f"PubChem records {first.title}'s molecular formula as "
                f"{first.molecular_formula}."
            )
        if kind == "weight":
            return (
                f"PubChem records {first.title}'s molecular weight as "
                f"{first.molecular_weight} g/mol."
            )
        property_answers = {
            "exact_mass": ("exact mass", first.exact_mass, "Da"),
            "logp": ("XLogP", first.xlogp, ""),
            "tpsa": ("topological polar surface area", first.tpsa, "A^2"),
            "hbd": ("hydrogen-bond donor count", first.hbond_donor_count, ""),
            "hba": ("hydrogen-bond acceptor count", first.hbond_acceptor_count, ""),
            "rotatable_bonds": ("rotatable-bond count", first.rotatable_bond_count, ""),
        }
        if kind in property_answers:
            label, value, unit = property_answers[kind]
            if value is None:
                return f"The frozen PubChem record for {first.title} does not report {label}."
            suffix = f" {unit}" if unit else ""
            return f"PubChem records {first.title}'s {label} as {value}{suffix}."
        if kind == "describe":
            return (
                f"PubChem identifies {first.title} (CID {first.cid}) as "
                f"{first.iupac_name}, formula {first.molecular_formula}, with molecular weight "
                f"{first.molecular_weight} g/mol."
            )
        second = records[1]
        same_formula = first.molecular_formula == second.molecular_formula
        same_connectivity = first.connectivity_smiles == second.connectivity_smiles
        different_stereo = first.isomeric_smiles != second.isomeric_smiles
        if same_formula and same_connectivity and different_stereo:
            return (
                f"{first.title} and {second.title} have the same formula "
                f"({first.molecular_formula}) and atom connectivity, but opposite stereochemical "
                f"configurations: {first.iupac_name} versus {second.iupac_name}. They are "
                "enantiomers."
            )
        differences = []
        if not same_formula:
            differences.append(
                f"formula ({first.molecular_formula} versus {second.molecular_formula})"
            )
        if not same_connectivity:
            differences.append("atom connectivity")
        if different_stereo:
            differences.append("stereochemical representation")
        detail = ", ".join(differences) or "no compared structured property"
        return f"PubChem distinguishes {first.title} and {second.title} by {detail}."
