import re
from collections.abc import Callable
from dataclasses import dataclass

from rdkit import Chem, rdBase
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdDepictor, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit.Chem.MolStandardize import rdMolStandardize

from app.core.chemistry_config import (
    DESCRIPTOR_CONFIGURATION,
    STANDARDIZATION_CONFIGURATION,
)
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
    method: str
    unit: str | None
    precision: int | None
    calculator: Callable[[Chem.Mol], str | float | int]
    tolerance: float | None = None


DESCRIPTOR_CALCULATORS: dict[str, Callable[[Chem.Mol], str | float | int]] = {
    "molecular_formula": rdMolDescriptors.CalcMolFormula,
    "molecular_weight": Descriptors.MolWt,
    "exact_mass": Descriptors.ExactMolWt,
    "logp": Crippen.MolLogP,
    "tpsa": rdMolDescriptors.CalcTPSA,
    "hbd": Lipinski.NumHDonors,
    "hba": Lipinski.NumHAcceptors,
    "rotatable_bonds": Lipinski.NumRotatableBonds,
    "ring_count": Lipinski.RingCount,
    "fraction_csp3": rdMolDescriptors.CalcFractionCSP3,
}

PROPERTY_SPECS = tuple(
    PropertySpec(
        key=definition["key"],
        label=definition["label"],
        method=definition["method"],
        unit=definition["unit"],
        precision=definition["precision"],
        calculator=DESCRIPTOR_CALCULATORS[definition["key"]],
        tolerance=definition["tolerance"],
    )
    for definition in DESCRIPTOR_CONFIGURATION
)


ISSUE_CONTENT = {
    "SMILES_SYNTAX_ERROR": {
        "title": "SMILES syntax error",
        "summary": "The molecular notation could not be parsed into a graph.",
        "explanation": "RDKit could not convert the submitted SMILES into a molecular graph.",
        "why_it_matters": (
            "Without a molecular graph, the application cannot calculate or compare properties."
        ),
        "next_step": (
            "Check brackets, branches, ring labels, atom symbols, charges, and bond characters."
        ),
    },
    "IMPOSSIBLE_VALENCE": {
        "title": "Impossible valence",
        "summary": "An atom has more bonds than its valence and charge permit.",
        "explanation": (
            "The graph contains an atom with an incompatible combination of bonds "
            "and formal charge."
        ),
        "why_it_matters": (
            "The structure is not chemically valid and cannot be used for safe "
            "property calculations."
        ),
        "next_step": (
            "Review the highlighted atom, formal charge, and surrounding bond orders "
            "in the source."
        ),
    },
    "AROMATICITY_ERROR": {
        "title": "Aromaticity could not be resolved",
        "summary": "The aromatic bond pattern cannot be converted to a consistent graph.",
        "explanation": "RDKit could not assign a valid Kekule representation to the graph.",
        "why_it_matters": (
            "Unresolved aromaticity prevents a safely sanitized molecular representation."
        ),
        "next_step": "Review aromatic atom notation, ring closure, and alternating bond patterns.",
    },
    "SANITIZATION_ERROR": {
        "title": "Chemical sanitization failed",
        "summary": "The parsed graph failed a chemical consistency check.",
        "explanation": "RDKit could not safely sanitize the parsed molecular graph.",
        "why_it_matters": (
            "A graph that fails sanitization cannot be used for reliable property calculations."
        ),
        "next_step": "Review the submitted charges, bonds, aromaticity, and atom specification.",
    },
    "RESOURCE_LIMIT_EXCEEDED": {
        "title": "Structure exceeds the analysis limit",
        "summary": "The molecular graph is too large or fragmented for this analysis profile.",
        "explanation": (
            "The structure parsed, but it exceeded a declared safety limit before expensive "
            "standardization or descriptor calculation began."
        ),
        "why_it_matters": (
            "Bounded inputs keep validation responsive and prevent one record from exhausting "
            "the analysis service."
        ),
        "next_step": "Submit one molecular entity at a time or reduce the source structure.",
    },
}

MAX_ATOMS = 2_000
MAX_FRAGMENTS = 100
RING_TOKEN = re.compile(r"%(?:\d{2})|\d")
INVALID_BOND_SEQUENCE = re.compile(r"(?:^|[.()])[-=#$:/\\]|[-=#$:/\\]{2,}")


def _syntax_issue(smiles: str) -> ValidationIssue:
    subcode = "UNPARSEABLE_SMILES"
    title = ISSUE_CONTENT["SMILES_SYNTAX_ERROR"]["title"]
    detail = "RDKit returned no molecular graph."
    start: int | None = None
    end: int | None = None

    if smiles.count("[") != smiles.count("]"):
        subcode = "UNMATCHED_BRACKET"
        title = "Unmatched square bracket"
        detail = "A bracketed atom expression is missing an opening or closing bracket."
        start = max(smiles.rfind("["), smiles.rfind("]"), 0)
        end = min(len(smiles), start + 1)
    elif smiles.count("(") != smiles.count(")"):
        subcode = "UNMATCHED_BRANCH"
        title = "Unmatched branch parenthesis"
        detail = "A SMILES branch is missing an opening or closing parenthesis."
        start = max(smiles.rfind("("), smiles.rfind(")"), 0)
        end = min(len(smiles), start + 1)
    else:
        ring_tokens = RING_TOKEN.findall(smiles)
        unmatched_ring = next(
            (token for token in dict.fromkeys(ring_tokens) if ring_tokens.count(token) % 2),
            None,
        )
        bond_match = INVALID_BOND_SEQUENCE.search(smiles)
        invalid_atom = re.search(r"(?<![A-Za-z])Q(?![a-z])", smiles)
        if unmatched_ring is not None:
            subcode = "UNCLOSED_RING"
            title = "Unclosed ring"
            detail = f"Ring label {unmatched_ring} does not have a matching closure."
            start = smiles.find(unmatched_ring)
            end = start + len(unmatched_ring)
        elif bond_match is not None:
            subcode = "INVALID_BOND_SEQUENCE"
            title = "Invalid bond placement"
            detail = "A bond symbol is misplaced or conflicts with an adjacent bond symbol."
            start, end = bond_match.span()
        elif invalid_atom is not None:
            subcode = "INVALID_ATOM_TOKEN"
            title = "Unknown atom token"
            detail = "The token Q is not a valid unbracketed SMILES element symbol."
            start, end = invalid_atom.span()

    content = ISSUE_CONTENT["SMILES_SYNTAX_ERROR"]
    return ValidationIssue(
        code="SMILES_SYNTAX_ERROR",
        subcode=subcode,
        title=title,
        severity=Severity.ERROR,
        summary=content["summary"],
        explanation=detail,
        why_it_matters=content["why_it_matters"],
        next_step=content["next_step"],
        location=IssueLocation(smiles_start=start, smiles_end=end),
        technical_detail=detail,
    )


def _invalid_issue(
    code: str,
    detail: str,
    atom_indices: list[int] | None = None,
) -> ValidationIssue:
    content = ISSUE_CONTENT[code]
    return ValidationIssue(
        code=code,
        title=content["title"],
        severity=Severity.ERROR,
        summary=content["summary"],
        explanation=content["explanation"],
        why_it_matters=content["why_it_matters"],
        next_step=content["next_step"],
        location=IssueLocation(atom_indices=atom_indices or []),
        technical_detail=detail,
    )


def _problem_atom_indices(problem: object) -> list[int]:
    if hasattr(problem, "GetAtomIdx"):
        return [int(problem.GetAtomIdx())]
    if hasattr(problem, "GetAtomIndices"):
        return [int(index) for index in problem.GetAtomIndices()]
    return []


def _sanitization_issue(
    problems: list[object],
    failure: Chem.SanitizeFlags,
) -> ValidationIssue:
    prioritized_types = ("AtomValenceException", "KekulizeException")
    problem = next(
        (
            candidate
            for problem_type in prioritized_types
            for candidate in problems
            if candidate.GetType() == problem_type
        ),
        problems[0] if problems else None,
    )
    problem_type = problem.GetType() if problem is not None else None
    if problem_type == "AtomValenceException" or failure == Chem.SanitizeFlags.SANITIZE_PROPERTIES:
        code = "IMPOSSIBLE_VALENCE"
    elif problem_type == "KekulizeException" or failure == Chem.SanitizeFlags.SANITIZE_KEKULIZE:
        code = "AROMATICITY_ERROR"
    else:
        code = "SANITIZATION_ERROR"
    detail = (
        problem.Message()
        if problem is not None
        else f"RDKit sanitization flag: {int(failure)}"
    )
    return _invalid_issue(
        code,
        detail,
        _problem_atom_indices(problem) if problem is not None else [],
    )


def _parse_and_validate(
    smiles: str,
) -> tuple[Chem.Mol | None, list[ValidationIssue], Chem.Mol | None]:
    with rdBase.BlockLogs():
        try:
            raw_mol = Chem.MolFromSmiles(smiles, sanitize=False)
        except Exception:
            raw_mol = None
    if raw_mol is None:
        return None, [_syntax_issue(smiles)], None

    atom_count = raw_mol.GetNumAtoms()
    fragment_count = len(Chem.GetMolFrags(raw_mol, sanitizeFrags=False))
    if atom_count > MAX_ATOMS or fragment_count > MAX_FRAGMENTS:
        detail = (
            f"Parsed graph contains {atom_count} atoms and {fragment_count} fragments; "
            f"limits are {MAX_ATOMS} atoms and {MAX_FRAGMENTS} fragments."
        )
        return (
            None,
            [_invalid_issue("RESOURCE_LIMIT_EXCEEDED", detail)],
            raw_mol,
        )

    unspecified_atoms = [atom.GetIdx() for atom in raw_mol.GetAtoms() if atom.GetAtomicNum() == 0]
    if unspecified_atoms:
        human_atoms = ", ".join(str(index + 1) for index in unspecified_atoms)
        return (
            None,
            [
                ValidationIssue(
                    code="UNSPECIFIED_ATOM",
                    title="Unspecified atom",
                    severity=Severity.ERROR,
                    summary="The structure contains a wildcard or query atom.",
                    explanation=(
                        f"Atom(s) {human_atoms} do not identify a chemical element, so the "
                        "molecular composition is incomplete."
                    ),
                    why_it_matters=(
                        "Properties such as formula, mass, and hydrogen-bond counts require every "
                        "atom to be defined."
                    ),
                    next_step=(
                        "Replace each wildcard (*) with the element shown in the source, or mark "
                        "the record as an unresolved generic structure."
                    ),
                    location=IssueLocation(atom_indices=unspecified_atoms),
                )
            ],
            raw_mol,
        )

    with rdBase.BlockLogs():
        try:
            problems = list(Chem.DetectChemistryProblems(raw_mol))
            sanitization_failure = Chem.SanitizeMol(raw_mol, catchErrors=True)
        except Exception as exc:
            issue = _invalid_issue(
                "SANITIZATION_ERROR",
                f"RDKit sanitization raised {type(exc).__name__}.",
            )
            return None, [issue], raw_mol
    if sanitization_failure != Chem.SanitizeFlags.SANITIZE_NONE:
        return None, [_sanitization_issue(problems, sanitization_failure)], raw_mol

    issues: list[ValidationIssue] = []
    Chem.AssignStereochemistry(raw_mol, force=True, cleanIt=True)
    unassigned_atoms: list[int] = []
    unassigned_bonds: list[int] = []
    for stereo in Chem.FindPotentialStereo(raw_mol, cleanIt=False, flagPossible=True):
        if stereo.specified != Chem.StereoSpecified.Unspecified:
            continue
        if stereo.type == Chem.StereoType.Atom_Tetrahedral:
            unassigned_atoms.append(int(stereo.centeredOn))
        elif stereo.type == Chem.StereoType.Bond_Double:
            unassigned_bonds.append(int(stereo.centeredOn))
    if unassigned_atoms or unassigned_bonds:
        affected = []
        if unassigned_atoms:
            affected.append("atom(s) " + ", ".join(str(index + 1) for index in unassigned_atoms))
        if unassigned_bonds:
            affected.append("bond(s) " + ", ".join(str(index + 1) for index in unassigned_bonds))
        issues.append(
            ValidationIssue(
                code="UNSPECIFIED_STEREOCHEMISTRY",
                title="Ambiguous stereochemistry",
                severity=Severity.WARNING,
                summary="One or more stereogenic features do not specify their arrangement.",
                explanation=(
                    f"Potential stereochemistry at {' and '.join(affected)} is not assigned."
                ),
                why_it_matters=(
                    "Different stereoisomers can have different biological activity and properties."
                ),
                next_step=(
                    "Check the paper or source diagram for wedge bonds or an explicit "
                    "stereochemical identifier."
                ),
                location=IssueLocation(
                    atom_indices=unassigned_atoms,
                    bond_indices=unassigned_bonds,
                ),
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


def _standardization_functions() -> dict[str, Callable[[Chem.Mol], Chem.Mol]]:
    tautomer_enumerator = rdMolStandardize.TautomerEnumerator()
    tautomer_enumerator.SetRemoveSp3Stereo(False)
    tautomer_enumerator.SetRemoveBondStereo(False)
    return {
        "CLEANUP": rdMolStandardize.Cleanup,
        "FRAGMENT_PARENT": rdMolStandardize.FragmentParent,
        "UNCHARGE": lambda molecule: rdMolStandardize.Uncharger().uncharge(molecule),
        "CANONICAL_TAUTOMER": tautomer_enumerator.Canonicalize,
    }


def _standardize(mol: Chem.Mol) -> tuple[Chem.Mol | None, list[StandardizationStep]]:
    steps: list[StandardizationStep] = []
    functions = _standardization_functions()
    current = Chem.Mol(mol)
    for definition in STANDARDIZATION_CONFIGURATION:
        code = definition["code"]
        label = definition["label"]
        before_smiles = Chem.MolToSmiles(current, isomericSmiles=True)
        try:
            after = functions[code](current)
        except Exception:
            steps.append(
                StandardizationStep(
                    code=code,
                    label=label,
                    before_smiles=before_smiles,
                    after_smiles=before_smiles,
                    changed=False,
                    status="failed",
                    reason_code="RDKIT_STANDARDIZATION_FAILURE",
                    reason=f"RDKit could not complete the {label.lower()} step.",
                )
            )
            return None, steps
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
        current = after
    return current, steps


def _depict(
    mol: Chem.Mol | None,
    highlight_atoms: list[int],
    highlight_bonds: list[int],
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
    computed: PropertyObservation,
    evidence: PropertyObservation,
    tolerance: float | None,
) -> ResultStatus:
    if computed.status != ResultStatus.AVAILABLE:
        return computed.status
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
            value = spec.calculator(mol)
            if spec.precision is not None and isinstance(value, float):
                value = round(value, spec.precision)
            computed = PropertyObservation(
                value=value,
                unit=spec.unit,
                status=ResultStatus.AVAILABLE,
            )
        except Exception as exc:
            computed = PropertyObservation(
                value=None,
                unit=spec.unit,
                status=ResultStatus.COMPUTATION_ERROR,
                reason_code="RDKIT_DESCRIPTOR_FAILURE",
                reason=f"RDKit could not calculate this descriptor ({type(exc).__name__}).",
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


def _standardization_failure_properties() -> list[PropertyComparison]:
    return [
        PropertyComparison(
            key=spec.key,
            label=spec.label,
            computed=PropertyObservation(
                value=None,
                unit=spec.unit,
                status=ResultStatus.COMPUTATION_ERROR,
                reason_code="STANDARDIZATION_FAILED",
                reason=(
                    "Properties were not calculated because molecular standardization failed."
                ),
            ),
            evidence=PropertyObservation(
                value=None,
                unit=spec.unit,
                status=ResultStatus.NOT_APPLICABLE,
                reason_code="NO_STANDARDIZED_STRUCTURE_FOR_LOOKUP",
                reason="Evidence lookup requires a successfully standardized structure.",
            ),
            comparison_status=ResultStatus.COMPUTATION_ERROR,
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
        status = (
            MoleculeStatus.AMBIGUOUS
            if any(issue.severity == Severity.WARNING for issue in issues)
            else MoleculeStatus.VALID
        )
        standardized_mol, steps = _standardize(molecule)
        if standardized_mol is None:
            standardized_smiles = None
            properties = _standardization_failure_properties()
        else:
            standardized_smiles = Chem.MolToSmiles(standardized_mol, isomericSmiles=True)
            properties = _properties(standardized_mol, standardized_smiles)

    response_payload = {
        "label": request.label or "Untitled molecule",
        "raw_input": request.structure,
        "input_type": "smiles",
        "source": request.source.model_dump(mode="json") if request.source else None,
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
