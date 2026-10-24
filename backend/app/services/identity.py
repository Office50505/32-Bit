from itertools import combinations

from rdkit import Chem, rdBase

from app.models.analysis import (
    AnalyzeResponse,
    MoleculeIdentityComparison,
    MoleculeRelationship,
    MoleculeStatus,
)


def _connectivity_smiles(smiles: str) -> str | None:
    with rdBase.BlockLogs():
        molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None
    return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=False)


def compare_molecule_identity(
    left: AnalyzeResponse,
    right: AnalyzeResponse,
    *,
    left_index: int,
    right_index: int,
) -> MoleculeIdentityComparison:
    common = {
        "left_index": left_index,
        "right_index": right_index,
        "left_standardized_smiles": left.standardized_smiles,
        "right_standardized_smiles": right.standardized_smiles,
    }
    if left.status == MoleculeStatus.INVALID or right.status == MoleculeStatus.INVALID:
        return MoleculeIdentityComparison(
            **common,
            relationship=MoleculeRelationship.INDETERMINATE,
            reason_code="INVALID_STRUCTURE_PREVENTS_IDENTITY_COMPARISON",
            reason="At least one input is invalid, so no molecular identity is assigned.",
        )
    if left.status == MoleculeStatus.AMBIGUOUS or right.status == MoleculeStatus.AMBIGUOUS:
        return MoleculeIdentityComparison(
            **common,
            relationship=MoleculeRelationship.INDETERMINATE,
            reason_code="UNSPECIFIED_STEREOCHEMISTRY_PREVENTS_EXACT_IDENTITY",
            reason=(
                "At least one input has unspecified stereochemistry, so an exact identity "
                "decision would be unsafe."
            ),
        )
    if not left.canonical_smiles or not right.canonical_smiles:
        return MoleculeIdentityComparison(
            **common,
            relationship=MoleculeRelationship.INDETERMINATE,
            reason_code="CANONICAL_IDENTITY_NOT_AVAILABLE",
            reason="A canonical molecular identity is unavailable for at least one input.",
        )
    if left.canonical_smiles == right.canonical_smiles:
        return MoleculeIdentityComparison(
            **common,
            relationship=MoleculeRelationship.EXACT_SAME_STRUCTURE,
            reason_code="CANONICAL_ISOMERIC_STRUCTURE_MATCH",
            reason=(
                "The inputs resolve to the same canonical structure, including defined "
                "stereochemistry and charge."
            ),
        )

    left_connectivity = _connectivity_smiles(left.canonical_smiles)
    right_connectivity = _connectivity_smiles(right.canonical_smiles)
    if left_connectivity is not None and left_connectivity == right_connectivity:
        return MoleculeIdentityComparison(
            **common,
            relationship=MoleculeRelationship.STEREOISOMERS,
            reason_code="CONNECTIVITY_MATCH_STEREOCHEMISTRY_DIFFERS",
            reason=(
                "The inputs have the same connectivity but different defined stereochemistry; "
                "they are not the same exact molecule."
            ),
        )
    if (
        left.standardized_smiles
        and right.standardized_smiles
        and left.standardized_smiles == right.standardized_smiles
    ):
        return MoleculeIdentityComparison(
            **common,
            relationship=MoleculeRelationship.SAME_STANDARDIZED_PARENT,
            reason_code="STANDARDIZED_COMPARISON_PARENT_MATCH",
            reason=(
                "The submitted forms differ, but the approved fragment, charge, and tautomer "
                "policy maps them to the same comparison parent."
            ),
        )
    return MoleculeIdentityComparison(
        **common,
        relationship=MoleculeRelationship.DIFFERENT_STRUCTURE,
        reason_code="STANDARDIZED_STRUCTURE_DIFFERS",
        reason="The standardized molecular structures are different.",
    )


def pairwise_identity_comparisons(
    results: list[AnalyzeResponse],
) -> list[MoleculeIdentityComparison]:
    return [
        compare_molecule_identity(
            results[left_index],
            results[right_index],
            left_index=left_index,
            right_index=right_index,
        )
        for left_index, right_index in combinations(range(len(results)), 2)
    ]
