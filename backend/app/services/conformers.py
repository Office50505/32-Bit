from __future__ import annotations

import hashlib
import json
from functools import lru_cache

from rdkit import Chem, rdBase
from rdkit.Chem import AllChem

from app.models.analysis import Conformer3D, ConformerAtom, ConformerBond

MAX_CONFORMER_HEAVY_ATOMS = 128
MAX_CONFORMER_TOTAL_ATOMS = 320
CONFORMER_SEED = 0x5EED


class ConformerGenerationError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _validated_molecule(structure: str) -> Chem.Mol:
    with rdBase.BlockLogs():
        molecule = Chem.MolFromSmiles(structure)
    if molecule is None:
        raise ConformerGenerationError(
            422,
            "INVALID_STRUCTURE",
            "A 3D conformer can only be generated for a valid standardized structure.",
        )
    if len(Chem.GetMolFrags(molecule)) != 1:
        raise ConformerGenerationError(
            422,
            "MULTIPLE_FRAGMENTS",
            "Generate the conformer from the standardized parent, not a salt or mixture.",
        )
    if molecule.GetNumHeavyAtoms() > MAX_CONFORMER_HEAVY_ATOMS:
        raise ConformerGenerationError(
            422,
            "CONFORMER_ATOM_LIMIT",
            f"3D generation supports up to {MAX_CONFORMER_HEAVY_ATOMS} heavy atoms.",
        )
    Chem.AssignStereochemistry(molecule, force=True, cleanIt=True)
    unspecified = [
        stereo
        for stereo in Chem.FindPotentialStereo(molecule, cleanIt=False, flagPossible=True)
        if stereo.specified == Chem.StereoSpecified.Unspecified
    ]
    if unspecified:
        raise ConformerGenerationError(
            409,
            "AMBIGUOUS_STEREOCHEMISTRY",
            "Confirm the molecule's stereochemistry before generating a computed 3D conformer.",
        )
    return molecule


@lru_cache(maxsize=256)
def generate_conformer(structure: str) -> Conformer3D:
    molecule = _validated_molecule(structure)
    canonical = Chem.MolToSmiles(molecule, isomericSmiles=True)
    embedded = Chem.AddHs(Chem.Mol(molecule))
    if embedded.GetNumAtoms() > MAX_CONFORMER_TOTAL_ATOMS:
        raise ConformerGenerationError(
            422,
            "CONFORMER_ATOM_LIMIT",
            f"3D generation supports up to {MAX_CONFORMER_TOTAL_ATOMS} atoms including hydrogen.",
        )

    parameters = AllChem.ETKDGv3()
    parameters.randomSeed = CONFORMER_SEED
    parameters.numThreads = 1
    parameters.maxIterations = 200
    if AllChem.EmbedMolecule(embedded, parameters) != 0:
        raise ConformerGenerationError(
            422,
            "CONFORMER_EMBEDDING_FAILED",
            "RDKit could not generate a stable 3D conformer for this structure.",
        )

    method = "ETKDGv3"
    try:
        if AllChem.MMFFHasAllMoleculeParams(embedded):
            AllChem.MMFFOptimizeMolecule(embedded, maxIters=250)
            method += " + MMFF94"
        elif AllChem.UFFHasAllMoleculeParams(embedded):
            AllChem.UFFOptimizeMolecule(embedded, maxIters=250)
            method += " + UFF"
    except (RuntimeError, ValueError):
        method += " · unoptimized"

    # Keep explicit hydrogens in the returned model. Removing them makes water,
    # ammonia, and methane collapse into a scientifically misleading lone atom.
    display = embedded
    conformer = display.GetConformer()
    points = [conformer.GetAtomPosition(index) for index in range(display.GetNumAtoms())]
    center_x = sum(point.x for point in points) / len(points)
    center_y = sum(point.y for point in points) / len(points)
    center_z = sum(point.z for point in points) / len(points)
    atoms = [
        ConformerAtom(
            element=atom.GetSymbol(),
            x=round(points[index].x - center_x, 6),
            y=round(points[index].y - center_y, 6),
            z=round(points[index].z - center_z, 6),
            formal_charge=atom.GetFormalCharge(),
        )
        for index, atom in enumerate(display.GetAtoms())
    ]
    bonds = [
        ConformerBond(
            begin=bond.GetBeginAtomIdx(),
            end=bond.GetEndAtomIdx(),
            order=1.5 if bond.GetIsAromatic() else bond.GetBondTypeAsDouble(),
        )
        for bond in display.GetBonds()
    ]
    coordinate_payload = {
        "canonical": canonical,
        "method": method,
        "seed": CONFORMER_SEED,
        "atoms": [atom.model_dump(mode="json") for atom in atoms],
        "bonds": [bond.model_dump(mode="json") for bond in bonds],
    }
    coordinate_sha256 = hashlib.sha256(
        json.dumps(coordinate_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return Conformer3D(
        method=method,
        coordinate_sha256=coordinate_sha256,
        atoms=atoms,
        bonds=bonds,
    )
