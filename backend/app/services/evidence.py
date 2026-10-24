from dataclasses import dataclass

from app.models.analysis import PropertyObservation, ResultStatus


@dataclass(frozen=True)
class EvidenceRecord:
    properties: dict[str, str | float | int]


# This deliberately small fixture supports UI and contract development only.
# It must never be labelled as a complete PubChem or ChEMBL snapshot.
DEMO_EVIDENCE: dict[str, EvidenceRecord] = {
    "CC(=O)Oc1ccccc1C(=O)O": EvidenceRecord(
        properties={
            "molecular_formula": "C9H8O4",
            "molecular_weight": 180.16,
            "exact_mass": 180.0423,
            "logp": 1.19,
            "tpsa": 63.6,
            "hbd": 1,
            "hba": 4,
            "rotatable_bonds": 2,
            "ring_count": 1,
            "fraction_csp3": 0.11,
        }
    )
}


def evidence_for(canonical_smiles: str, key: str, unit: str | None) -> PropertyObservation:
    record = DEMO_EVIDENCE.get(canonical_smiles)
    if record is None:
        return PropertyObservation(
            value=None,
            unit=unit,
            status=ResultStatus.OUTSIDE_SNAPSHOT_COVERAGE,
            reason_code="DEMO_FIXTURE_OUTSIDE_COVERAGE",
            reason=(
                "This molecule is not covered by the bundled development fixture. "
                "This does not establish absence from full PubChem or ChEMBL."
            ),
        )
    if key not in record.properties:
        return PropertyObservation(
            value=None,
            unit=unit,
            status=ResultStatus.NOT_AVAILABLE,
            reason_code="PROPERTY_NOT_REPORTED",
            reason="A matching fixture record exists, but this property is not reported.",
        )
    return PropertyObservation(
        value=record.properties[key],
        unit=unit,
        status=ResultStatus.AVAILABLE,
    )
