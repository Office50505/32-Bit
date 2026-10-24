from app.models.analysis import PropertyObservation, ResultStatus


def evidence_for(_canonical_smiles: str, _key: str, unit: str | None) -> PropertyObservation:
    """Return an explicit missing state until a verified frozen snapshot is configured."""
    return PropertyObservation(
        value=None,
        unit=unit,
        status=ResultStatus.NOT_AVAILABLE,
        reason_code="REFERENCE_SNAPSHOT_NOT_CONFIGURED",
        reason=(
            "No frozen PubChem or ChEMBL snapshot is configured in this build, so a "
            "reference value cannot be reported."
        ),
    )
