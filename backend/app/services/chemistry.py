from collections.abc import Callable
from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdDepictor, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit.Chem.MolStandardize import rdMolStandardize

from app.core.provenance import create_manifest
from app.models.analysis import (
    AnalyzeRequest,
    AnalyzeResponse,
    IssueLocation,
    MoleculeStatus,
    PropertyComparison,
    PropertyObservation,
    ResultStatus,
    Severity,
    StandardizationStep,
    ValidationIssue,
)
from app.services.evidence import evidence_for


@dataclass(frozen=True)
class PropertySpec:
    key: str
    label: str
    unit: str | None
    calculator: Callable[[Chem.Mol], str | float | int]
    tolerance: float | None = None


PROPERTY_SPECS = (
    PropertySpec("molecular_formula", "Molecular formula", None, rdMolDescriptors.CalcMolFormula),
    PropertySpec(
        "molecular_weight",
        "Molecular weight",
        "g/mol",
        lambda m: round(Descriptors.MolWt(m), 2),
        0.02,
    ),
    PropertySpec(
        "exact_mass", "Exact mass", "Da", lambda m: round(Descriptors.ExactMolWt(m), 4), 0.001
    ),
    PropertySpec("logp", "LogP", None, lambda m: round(Crippen.MolLogP(m), 2), 0.15),
    PropertySpec(
        "tpsa",
        "Topological polar surface area",
        "Å²",
        lambda m: round(rdMolDescriptors.CalcTPSA(m), 2),
        0.1,
    ),
    PropertySpec("hbd", "Hydrogen-bond donors", None, Lipinski.NumHDonors),
    PropertySpec("hba", "Hydrogen-bond acceptors", None, Lipinski.NumHAcceptors),
    PropertySpec("rotatable_bonds", "Rotatable bonds", None, Lipinski.NumRotatableBonds),
    PropertySpec("ring_count", "Ring count", None, Lipinski.RingCount),
    PropertySpec(
        "fraction_csp3",
        "Fraction Csp³",
        None,
        lambda m: round(rdMolDescriptors.CalcFractionCSP3(m), 2),
        0.01,
    ),
)


def _invalid_issue(
    code: str, title: str, detail: str, atom_index: int | None = None
) -> ValidationIssue:
    location = IssueLocation(atom_indices=[atom_index] if atom_index is not None else [])
    if code == "IMPOSSIBLE_VALENCE":
        return ValidationIssue(
            code=code,
            title=title,
            severity=Severity.ERROR,
            summary="An atom has more bonds than its valence and charge permit.",
            explanation=(
                f"Atom {atom_index + 1 if atom_index is not None else 'at the reported position'} "
                "has an incompatible combination of bonds and formal charge."
            ),
            why_it_matters=(
                "The structure is not chemically valid and cannot be used for safe "
                "property calculations."
            ),
            next_step=(
                "Review the highlighted atom, formal charge, and surrounding bond "
                "orders in the source."
            ),
            location=location,
            technical_detail=detail,
        )
    return ValidationIssue(
        code=code,
        title=title,
        severity=Severity.ERROR,
        summary="The molecular notation could not be interpreted safely.",
        explanation="The submitted SMILES could not be converted into a valid molecular graph.",
        why_it_matters=(
            "Without a molecular graph, the application cannot calculate or compare properties."
        ),
        next_step=(
            "Check brackets, branches, ring labels, atom symbols, charges, and bond characters."
        ),
        location=location,
        technical_detail=detail,
    )


def _parse_and_validate(
    smiles: str,
) -> tuple[Chem.Mol | None, list[ValidationIssue], Chem.Mol | None]:
    raw_mol = Chem.MolFromSmiles(smiles, sanitize=False)
    if raw_mol is None:
        return (
            None,
            [
                _invalid_issue(
                    "SMILES_SYNTAX_ERROR",
                    "SMILES syntax error",
                    "RDKit returned no molecular graph.",
                )
            ],
            None,
        )

    try:
        Chem.SanitizeMol(raw_mol)
    except Exception as exc:  # RDKit exposes several native exception subclasses.
        detail = str(exc)
        atom_index = exc.GetAtomIdx() if hasattr(exc, "GetAtomIdx") else None
        if "valence" in detail.lower():
            issue = _invalid_issue("IMPOSSIBLE_VALENCE", "Impossible valence", detail, atom_index)
        elif "kekul" in detail.lower():
            issue = _invalid_issue(
                "AROMATICITY_ERROR", "Aromaticity could not be resolved", detail, atom_index
            )
        else:
            issue = _invalid_issue(
                "SANITIZATION_ERROR", "Chemical sanitization failed", detail, atom_index
            )
        return None, [issue], raw_mol

    issues: list[ValidationIssue] = []
    Chem.AssignStereochemistry(raw_mol, force=True, cleanIt=True)
    unassigned_centers = [
        atom_index
        for atom_index, label in Chem.FindMolChiralCenters(
            raw_mol,
            includeUnassigned=True,
            includeCIP=True,
            useLegacyImplementation=False,
        )
        if label == "?"
    ]
    if unassigned_centers:
        human_atoms = ", ".join(str(index + 1) for index in unassigned_centers)
        issues.append(
            ValidationIssue(
                code="UNSPECIFIED_STEREOCHEMISTRY",
                title="Ambiguous stereochemistry",
                severity=Severity.WARNING,
                summary="One or more stereogenic atoms do not specify their spatial arrangement.",
                explanation=(
                    f"Potential stereocentre(s) at atom(s) {human_atoms} are not assigned "
                    "R/S configuration."
                ),
                why_it_matters=(
                    "Different stereoisomers can have different biological activity and properties."
                ),
                next_step=(
                    "Check the paper or source diagram for wedge bonds or an explicit "
                    "stereochemical identifier."
                ),
                location=IssueLocation(atom_indices=unassigned_centers),
            )
        )

    fragments = Chem.GetMolFrags(raw_mol)
    if len(fragments) > 1:
        issues.append(
            ValidationIssue(
                code="MULTIPLE_FRAGMENTS",
                title="Multiple disconnected components",
                severity=Severity.INFO,
                summary=f"The input contains {len(fragments)} disconnected components.",
                explanation=(
                    "The structure may represent a salt, solvent, mixture, or "
                    "multicomponent compound."
                ),
                why_it_matters=(
                    "Parent selection can change identity matching and calculated properties."
                ),
                next_step="Review the standardization record before comparing the selected parent.",
            )
        )

    return raw_mol, issues, raw_mol


def _standardize(mol: Chem.Mol) -> tuple[Chem.Mol, list[StandardizationStep]]:
    steps: list[StandardizationStep] = []

    def apply_step(code: str, label: str, before: Chem.Mol, after: Chem.Mol) -> Chem.Mol:
        before_smiles = Chem.MolToSmiles(before, isomericSmiles=True)
        after_smiles = Chem.MolToSmiles(after, isomericSmiles=True)
        steps.append(
            StandardizationStep(
                code=code,
                label=label,
                before_smiles=before_smiles,
                after_smiles=after_smiles,
                changed=before_smiles != after_smiles,
            )
        )
        return after

    current = Chem.Mol(mol)
    current = apply_step(
        "CLEANUP",
        "Normalize functional groups and charges",
        current,
        rdMolStandardize.Cleanup(current),
    )
    current = apply_step(
        "FRAGMENT_PARENT",
        "Select the parent fragment",
        current,
        rdMolStandardize.FragmentParent(current),
    )
    current = apply_step(
        "UNCHARGE",
        "Normalize removable formal charges",
        current,
        rdMolStandardize.Uncharger().uncharge(current),
    )
    current = apply_step(
        "CANONICAL_TAUTOMER",
        "Select the canonical tautomer",
        current,
        rdMolStandardize.TautomerEnumerator().Canonicalize(current),
    )
    return current, steps


def _depict(
    mol: Chem.Mol | None, highlight_atoms: list[int], highlight_bonds: list[int]
) -> str | None:
    if mol is None:
        return None
    depiction = Chem.Mol(mol)
    try:
        depiction.UpdatePropertyCache(strict=False)
        rdDepictor.Compute2DCoords(depiction)
        drawer = rdMolDraw2D.MolDraw2DSVG(620, 360)
        options = drawer.drawOptions()
        options.clearBackground = False
        options.addAtomIndices = bool(highlight_atoms)
        options.bondLineWidth = 2
        color = (0.82, 0.08, 0.16, 1.0)
        drawer.DrawMolecule(
            depiction,
            highlightAtoms=highlight_atoms,
            highlightBonds=highlight_bonds,
            highlightAtomColors={index: color for index in highlight_atoms},
            highlightBondColors={index: color for index in highlight_bonds},
        )
        drawer.FinishDrawing()
        return drawer.GetDrawingText()
    except Exception:
        return None


def _comparison_status(
    computed: PropertyObservation, evidence: PropertyObservation, tolerance: float | None
) -> ResultStatus:
    if evidence.status != ResultStatus.AVAILABLE:
        return evidence.status
    if computed.value is None or evidence.value is None:
        return ResultStatus.NOT_COMPUTABLE
    if isinstance(computed.value, (int, float)) and isinstance(evidence.value, (int, float)):
        allowed = tolerance if tolerance is not None else 0
        return (
            ResultStatus.AVAILABLE
            if abs(float(computed.value) - float(evidence.value)) <= allowed
            else ResultStatus.CONFLICTING_EVIDENCE
        )
    return (
        ResultStatus.AVAILABLE
        if computed.value == evidence.value
        else ResultStatus.CONFLICTING_EVIDENCE
    )


def _properties(mol: Chem.Mol, canonical_smiles: str) -> list[PropertyComparison]:
    results: list[PropertyComparison] = []
    for spec in PROPERTY_SPECS:
        try:
            computed = PropertyObservation(
                value=spec.calculator(mol), unit=spec.unit, status=ResultStatus.AVAILABLE
            )
        except Exception as exc:
            computed = PropertyObservation(
                value=None,
                unit=spec.unit,
                status=ResultStatus.COMPUTATION_ERROR,
                reason_code="RDKIT_DESCRIPTOR_FAILURE",
                reason=f"RDKit could not calculate this descriptor: {exc}",
            )
        evidence = evidence_for(canonical_smiles, spec.key, spec.unit)
        results.append(
            PropertyComparison(
                key=spec.key,
                label=spec.label,
                computed=computed,
                evidence=evidence,
                comparison_status=_comparison_status(computed, evidence, spec.tolerance),
            )
        )
    return results


def _invalid_properties() -> list[PropertyComparison]:
    reason = "Properties were not calculated because the submitted structure is chemically invalid."
    return [
        PropertyComparison(
            key=spec.key,
            label=spec.label,
            computed=PropertyObservation(
                value=None,
                unit=spec.unit,
                status=ResultStatus.INVALID_INPUT,
                reason_code="INVALID_STRUCTURE_BLOCKS_CALCULATION",
                reason=reason,
            ),
            evidence=PropertyObservation(
                value=None,
                unit=spec.unit,
                status=ResultStatus.NOT_APPLICABLE,
                reason_code="NO_VALID_STRUCTURE_FOR_LOOKUP",
                reason="Evidence lookup is not applicable until the structure is valid.",
            ),
            comparison_status=ResultStatus.INVALID_INPUT,
        )
        for spec in PROPERTY_SPECS
    ]


def analyze_structure(request: AnalyzeRequest) -> AnalyzeResponse:
    molecule, issues, depiction_mol = _parse_and_validate(request.structure)
    highlight_atoms = [index for issue in issues for index in issue.location.atom_indices]
    highlight_bonds = [index for issue in issues for index in issue.location.bond_indices]

    if molecule is None:
        status = MoleculeStatus.INVALID
        canonical_smiles = None
        standardized_smiles = None
        steps: list[StandardizationStep] = []
        properties = _invalid_properties()
    else:
        canonical_smiles = Chem.MolToSmiles(molecule, isomericSmiles=True)
        standardized_mol, steps = _standardize(molecule)
        standardized_smiles = Chem.MolToSmiles(standardized_mol, isomericSmiles=True)
        properties = _properties(standardized_mol, standardized_smiles)
        status = (
            MoleculeStatus.AMBIGUOUS
            if any(issue.severity == Severity.WARNING for issue in issues)
            else MoleculeStatus.VALID
        )

    response_payload = {
        "label": request.label or "Untitled molecule",
        "raw_input": request.structure,
        "status": status,
        "canonical_smiles": canonical_smiles,
        "standardized_smiles": standardized_smiles,
        "issues": [issue.model_dump(mode="json") for issue in issues],
        "standardization_steps": [step.model_dump(mode="json") for step in steps],
        "properties": [prop.model_dump(mode="json") for prop in properties],
    }
    manifest = create_manifest(request.model_dump(mode="json"), response_payload)
    return AnalyzeResponse(
        analysis_id=manifest.analysis_id,
        label=request.label or "Untitled molecule",
        raw_input=request.structure,
        input_type="smiles",
        status=status,
        canonical_smiles=canonical_smiles,
        standardized_smiles=standardized_smiles,
        depiction_svg=_depict(depiction_mol, highlight_atoms, highlight_bonds),
        issues=issues,
        standardization_steps=steps,
        properties=properties,
        source=request.source,
        manifest=manifest,
    )
