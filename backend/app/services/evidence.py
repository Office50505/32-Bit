import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rdkit import Chem

from app.models.analysis import PropertyObservation, ResultStatus
from app.services.pubchem_questions import (
    FrozenPubChemClient,
    FrozenPubChemCompound,
    PubChemCompoundNotFoundError,
    PubChemQuestionError,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_RUNTIME_CACHE = _PROJECT_ROOT / "data/runtime/pubchem-compound-snapshots"
_DEFAULT_BUNDLED_SNAPSHOTS = _PROJECT_ROOT / "data/snapshots/pubchem-compounds"


@dataclass(frozen=True, slots=True)
class PropertyEvidenceResolution:
    snapshot_id: str
    snapshot_scope: str
    missing_status: ResultStatus = ResultStatus.NOT_AVAILABLE
    record: FrozenPubChemCompound | None = None
    reason_code: str | None = None
    reason: str | None = None


def _property_evidence_enabled() -> bool:
    value = os.environ.get("PROVENANCELAB_PROPERTY_EVIDENCE", "1")
    return value.casefold().strip() not in {"0", "false", "no", "off"}


@lru_cache(maxsize=1)
def _pubchem_client() -> FrozenPubChemClient:
    runtime_cache = os.environ.get(
        "PROVENANCELAB_PUBCHEM_CACHE",
        str(_DEFAULT_RUNTIME_CACHE),
    )
    bundled = os.environ.get(
        "PROVENANCELAB_PUBCHEM_BUNDLED_SNAPSHOTS",
        str(_DEFAULT_BUNDLED_SNAPSHOTS),
    )
    return FrozenPubChemClient(
        runtime_cache,
        fallback_directories=(bundled,),
        base_url=os.environ.get(
            "PROVENANCELAB_PUBCHEM_URL",
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug",
        ),
    )


def resolve_property_evidence(
    canonical_smiles: str,
    *,
    client: FrozenPubChemClient | None = None,
    enabled: bool | None = None,
) -> PropertyEvidenceResolution:
    if enabled is None:
        enabled = _property_evidence_enabled()
    if not enabled:
        return PropertyEvidenceResolution(
            snapshot_id="not-configured",
            snapshot_scope="Frozen PubChem property evidence is disabled for this run.",
            reason_code="REFERENCE_SNAPSHOT_NOT_CONFIGURED",
            reason=(
                "No frozen PubChem property snapshot is configured for this run, so a "
                "reference value cannot be reported."
            ),
        )

    molecule = Chem.MolFromSmiles(canonical_smiles)
    inchikey = Chem.MolToInchiKey(molecule) if molecule is not None else ""
    if not inchikey:
        return PropertyEvidenceResolution(
            snapshot_id="pubchem-lookup-not-applicable",
            snapshot_scope="No PubChem identifier could be derived from the standardized graph.",
            reason_code="PUBCHEM_IDENTIFIER_UNAVAILABLE",
            reason="The standardized structure could not be converted to an InChIKey.",
        )

    try:
        record = (client or _pubchem_client()).get_by_inchikey(inchikey)
    except PubChemCompoundNotFoundError:
        return PropertyEvidenceResolution(
            snapshot_id="pubchem-no-reference-match",
            snapshot_scope=(
                "PubChem returned no CID for the standardized structure's exact InChIKey."
            ),
            missing_status=ResultStatus.NO_REFERENCE_MATCH,
            reason_code="PUBCHEM_NO_CID_FOR_INCHIKEY",
            reason=(
                "No PubChem CID matches this exact standardized structure. The local RDKit "
                "value is still reported separately."
            ),
        )
    except PubChemQuestionError:
        return PropertyEvidenceResolution(
            snapshot_id="pubchem-pug-unavailable",
            snapshot_scope="PubChem acquisition failed; computed values remain available.",
            reason_code="PUBCHEM_SNAPSHOT_ACQUISITION_FAILED",
            reason=(
                "The PubChem reference record could not be acquired or verified. The local "
                "RDKit value is still reported separately."
            ),
        )
    if record.inchikey != inchikey:
        return PropertyEvidenceResolution(
            snapshot_id=record.snapshot_id,
            snapshot_scope="Frozen PubChem record did not match the standardized InChIKey.",
            reason_code="PUBCHEM_IDENTITY_MISMATCH",
            reason=(
                "The frozen PubChem record resolves to a different molecular identity, so its "
                "properties were not compared."
            ),
        )
    return PropertyEvidenceResolution(
        snapshot_id=record.snapshot_id,
        snapshot_scope=(
            f"Frozen PubChem compound record CID {record.cid}; exact response bytes verified "
            f"by SHA-256 {record.raw_sha256}."
        ),
        record=record,
    )


def evidence_for(
    resolution: PropertyEvidenceResolution,
    key: str,
    unit: str | None,
) -> PropertyObservation:
    record = resolution.record
    if record is None:
        return PropertyObservation(
            value=None,
            unit=unit,
            status=resolution.missing_status,
            reason_code=resolution.reason_code or "REFERENCE_RECORD_UNAVAILABLE",
            reason=resolution.reason or "No verified reference record is available.",
        )

    values: dict[str, str | float | int | None] = {
        "molecular_formula": record.molecular_formula,
        "molecular_weight": (
            float(record.molecular_weight) if record.molecular_weight is not None else None
        ),
        "exact_mass": float(record.exact_mass) if record.exact_mass is not None else None,
        "logp": record.xlogp,
        "tpsa": record.tpsa,
        "hbd": record.hbond_donor_count,
        "hba": record.hbond_acceptor_count,
        "rotatable_bonds": record.rotatable_bond_count,
        "ring_count": None,
        "fraction_csp3": None,
    }
    value = values.get(key)
    if value is None:
        return PropertyObservation(
            value=None,
            unit=unit,
            status=ResultStatus.OUTSIDE_SNAPSHOT_COVERAGE,
            reason_code="PUBCHEM_PROPERTY_NOT_IN_SNAPSHOT",
            reason=(
                f"Frozen PubChem CID {record.cid} does not report this property in the "
                "configured compound-property snapshot."
            ),
        )
    return PropertyObservation(
        value=value,
        unit=unit,
        status=ResultStatus.AVAILABLE,
        reason_code="FROZEN_PUBCHEM_COMPOUND_RECORD",
        reason=(
            f"Frozen PubChem CID {record.cid}; source response SHA-256 "
            f"{record.raw_sha256[:12]}…."
        ),
    )
