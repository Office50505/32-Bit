CHEMISTRY_POLICY_VERSION = "phase1-approved.1"
VALIDATION_POLICY_VERSION = "rdkit-structured-problems-v2"
OUTPUT_SCHEMA_VERSION = "analysis-response-v2-identity-replay"
CANONICAL_SERIALIZATION_VERSION = "json-sort-keys-compact-utf8-finite-v1"

VALIDATION_CONFIGURATION = {
    "parser": "Chem.MolFromSmiles(sanitize=False)",
    "sanitizer": "Chem.SanitizeMol(catchErrors=True)",
    "problem_classifier": "Chem.DetectChemistryProblems",
    "problem_priority": [
        "AtomValenceException",
        "KekulizeException",
        "other-sanitization-failure",
    ],
    "stereo_detector": "Chem.FindPotentialStereo",
    "unspecified_stereo_is_ambiguous": True,
}

INPUT_NORMALIZATION_CONFIGURATION = {
    "non_ring_aromatic_atom_case": {
        "enabled": True,
        "trigger": "lowercase aromatic atom outside a ring",
        "action": "clear aromatic flags and interpret the affected atoms as aliphatic",
        "preserve_raw_input": True,
        "emit_audit_issue": "ATOM_CASE_NORMALIZED",
        "emit_audit_step": "NORMALIZE_NON_RING_ATOM_CASE",
    }
}

DEPICTION_CONFIGURATION = {
    "atom_palette": "black-and-white",
    "normal_bonds": "neutral",
    "validation_highlight_rgba": [0.82, 0.08, 0.16, 1.0],
    "reason": "reserve red for explicit validation findings",
}

STANDARDIZATION_CONFIGURATION = (
    {
        "code": "CLEANUP",
        "label": "Normalize functional groups and charges",
        "method": "rdMolStandardize.Cleanup",
    },
    {
        "code": "FRAGMENT_PARENT",
        "label": "Select the parent fragment",
        "method": "rdMolStandardize.FragmentParent",
    },
    {
        "code": "UNCHARGE",
        "label": "Normalize removable formal charges",
        "method": "rdMolStandardize.Uncharger.uncharge",
    },
    {
        "code": "CANONICAL_TAUTOMER",
        "label": "Select the canonical tautomer",
        "method": "rdMolStandardize.TautomerEnumerator.Canonicalize",
    },
)

DESCRIPTOR_CONFIGURATION = (
    {
        "key": "molecular_formula",
        "label": "Molecular formula",
        "method": "rdMolDescriptors.CalcMolFormula",
        "unit": None,
        "precision": None,
        "tolerance": None,
    },
    {
        "key": "molecular_weight",
        "label": "Molecular weight",
        "method": "Descriptors.MolWt",
        "unit": "g/mol",
        "precision": 2,
        "tolerance": 0.02,
    },
    {
        "key": "exact_mass",
        "label": "Exact mass",
        "method": "Descriptors.ExactMolWt",
        "unit": "Da",
        "precision": 4,
        "tolerance": 0.001,
    },
    {
        "key": "logp",
        "label": "LogP",
        "method": "Crippen.MolLogP",
        "unit": "unitless",
        "precision": 2,
        "tolerance": 0.15,
    },
    {
        "key": "tpsa",
        "label": "Topological polar surface area",
        "method": "rdMolDescriptors.CalcTPSA",
        "unit": "A^2",
        "precision": 2,
        "tolerance": 0.1,
    },
    {
        "key": "hbd",
        "label": "Hydrogen-bond donors",
        "method": "Lipinski.NumHDonors",
        "unit": "count",
        "precision": 0,
        "tolerance": None,
    },
    {
        "key": "hba",
        "label": "Hydrogen-bond acceptors",
        "method": "Lipinski.NumHAcceptors",
        "unit": "count",
        "precision": 0,
        "tolerance": None,
    },
    {
        "key": "rotatable_bonds",
        "label": "Rotatable bonds",
        "method": "Lipinski.NumRotatableBonds",
        "unit": "count",
        "precision": 0,
        "tolerance": None,
    },
    {
        "key": "ring_count",
        "label": "Ring count",
        "method": "Lipinski.RingCount",
        "unit": "count",
        "precision": 0,
        "tolerance": None,
    },
    {
        "key": "fraction_csp3",
        "label": "Fraction Csp3",
        "method": "rdMolDescriptors.CalcFractionCSP3",
        "unit": "unitless",
        "precision": 2,
        "tolerance": 0.01,
    },
)
