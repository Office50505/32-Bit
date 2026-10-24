import json
import math
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rdkit import Chem

from app.core.chemistry_config import DESCRIPTOR_CONFIGURATION
from app.core.provenance import (
    canonical_json,
    configuration_payload,
    configuration_sha256,
)
from app.main import app
from app.models.analysis import (
    AnalyzeRequest,
    MoleculeStatus,
    PropertyObservation,
    ResultStatus,
    Severity,
)
from app.services import chemistry

CORPUS_PATH = Path(__file__).parent / "fixtures" / "phase1_chemistry_corpus.json"
CORPUS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
CASES = CORPUS["cases"]
STANDARDIZATION_ORDER = [
    "CLEANUP",
    "FRAGMENT_PARENT",
    "UNCHARGE",
    "CANONICAL_TAUTOMER",
]
EXPECTED_CATEGORY_COUNTS = {
    "syntax_ring_closure": 6,
    "valence_sanitization_aromaticity": 6,
    "stereochemistry_geometry": 5,
    "salts_solvents_fragments": 4,
    "charge_protonation": 3,
    "tautomer_equivalent_form": 3,
    "evidence_missing_semantics": 4,
}
client = TestClient(app)


def analyze_case(case: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/api/analyze",
        json={
            "structure": case["input"]["structure"],
            "input_type": case["input"]["format"],
            "label": case["case_id"],
        },
    )
    assert response.status_code == 200
    return response.json()


def assert_missing_observation_has_reason(observation: dict[str, Any]) -> None:
    if observation["value"] is None:
        assert observation["reason_code"]
        assert observation["reason"]


def test_corpus_shape_and_allocation() -> None:
    assert CORPUS["schema_version"] == "phase1-corpus-v1"
    assert CORPUS["approval_state"] == "approved"
    assert len(CASES) == 31
    assert len({case["case_id"] for case in CASES}) == 31
    assert Counter(case["category"] for case in CASES) == EXPECTED_CATEGORY_COUNTS
    assert {case["input"]["format"] for case in CASES} == {"smiles"}
    # Per-case values preserve their authored-candidate provenance; corpus-level approval
    # signs the exact set as a whole.
    assert {case["expectation_status"] for case in CASES} == {"proposed"}
    assert all(case["reason"] for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_phase1_corpus_case_and_three_run_determinism(case: dict[str, Any]) -> None:
    runs = [analyze_case(case) for _ in range(3)]
    first = runs[0]
    expected = case["expected"]

    assert first["raw_input"] == case["input"]["structure"]
    assert first["input_type"] == case["input"]["format"]
    assert first["status"] == expected["classification"]
    assert first["canonical_smiles"] == expected["canonical_smiles"]

    expected_issues = expected["issues"]
    assert [issue["code"] for issue in first["issues"]] == [
        issue["code"] for issue in expected_issues
    ]
    assert [issue["severity"] for issue in first["issues"]] == [
        issue["severity"] for issue in expected_issues
    ]
    for actual_issue, expected_issue in zip(first["issues"], expected_issues, strict=True):
        if "location" in expected_issue:
            assert actual_issue["location"]["atom_indices"] == expected_issue["location"][
                "atom_indices"
            ]
            assert actual_issue["location"]["bond_indices"] == expected_issue["location"][
                "bond_indices"
            ]
        assert actual_issue["title"]
        assert actual_issue["summary"]
        assert actual_issue["explanation"]
        assert actual_issue["why_it_matters"]
        assert actual_issue["next_step"]

    standardization = expected["standardization"]
    if standardization["outcome"] == "not_run":
        assert first["standardization_steps"] == []
        assert first["standardized_smiles"] is None
    else:
        assert [step["code"] for step in first["standardization_steps"]] == (
            STANDARDIZATION_ORDER
        )
        assert all(step["status"] == "applied" for step in first["standardization_steps"])
        assert [
            step["code"] for step in first["standardization_steps"] if step["changed"]
        ] == standardization["changed_steps"]
        assert first["standardized_smiles"] == standardization["standardized_smiles"]

    assert len(first["properties"]) == 10
    for prop in first["properties"]:
        computed = prop["computed"]
        evidence = prop["evidence"]
        assert computed["status"] == expected["descriptors"]["status"]
        if expected["descriptors"]["values"] == "present":
            assert computed["value"] is not None
        else:
            assert computed["value"] is None
        assert evidence["status"] == expected["evidence"]["status"]
        assert evidence["reason_code"] == expected["evidence"]["reason_code"]
        assert_missing_observation_has_reason(computed)
        assert_missing_observation_has_reason(evidence)

    for hash_key in ("input_sha256", "configuration_sha256", "output_sha256"):
        assert len({run["manifest"][hash_key] for run in runs}) == 1
        assert len(first["manifest"][hash_key]) == 64
    for stable_key in ("issues", "standardization_steps", "properties"):
        assert all(run[stable_key] == first[stable_key] for run in runs[1:])


def test_whitespace_only_input_is_a_malformed_request() -> None:
    for structure in ("", " ", "\t\r\n"):
        response = client.post("/api/analyze", json={"structure": structure})
        assert response.status_code == 422


def test_exact_nonblank_input_text_is_preserved_and_hashed() -> None:
    plain = client.post("/api/analyze", json={"structure": "CCO"})
    padded = client.post("/api/analyze", json={"structure": " CCO "})
    assert plain.status_code == 200
    assert padded.status_code == 200
    assert padded.json()["raw_input"] == " CCO "
    assert plain.json()["manifest"]["input_sha256"] != padded.json()["manifest"]["input_sha256"]


def test_all_ten_descriptor_definitions_for_ethanol() -> None:
    result = analyze_case(next(case for case in CASES if case["case_id"] == "EVID-001"))
    observations = {
        prop["key"]: (prop["computed"]["value"], prop["computed"]["unit"])
        for prop in result["properties"]
    }
    assert observations == {
        "molecular_formula": ("C2H6O", None),
        "molecular_weight": (46.07, "g/mol"),
        "exact_mass": (46.0419, "Da"),
        "logp": (-0.0, "unitless"),
        "tpsa": (20.23, "A^2"),
        "hbd": (1, "count"),
        "hba": (1, "count"),
        "rotatable_bonds": (0, "count"),
        "ring_count": (0, "count"),
        "fraction_csp3": (1.0, "unitless"),
    }
    assert [definition["key"] for definition in DESCRIPTOR_CONFIGURATION] == list(observations)


def test_descriptor_failure_is_explicit_and_not_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_descriptor(_molecule: Chem.Mol) -> float:
        raise RuntimeError("controlled test failure")

    failing_spec = replace(chemistry.PROPERTY_SPECS[0], calculator=fail_descriptor)
    monkeypatch.setattr(
        chemistry,
        "PROPERTY_SPECS",
        (failing_spec, *chemistry.PROPERTY_SPECS[1:]),
    )
    result = chemistry.analyze_structure(AnalyzeRequest(structure="CCO"))
    observation = result.properties[0]
    assert observation.computed.value is None
    assert observation.computed.status == ResultStatus.COMPUTATION_ERROR
    assert observation.computed.reason_code == "RDKIT_DESCRIPTOR_FAILURE"
    assert observation.computed.reason
    assert observation.comparison_status == ResultStatus.COMPUTATION_ERROR


def test_standardization_failure_is_logged_and_blocks_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    functions = chemistry._standardization_functions()

    def fail_fragment_parent(_molecule: Chem.Mol) -> Chem.Mol:
        raise RuntimeError("controlled test failure")

    functions["FRAGMENT_PARENT"] = fail_fragment_parent
    monkeypatch.setattr(chemistry, "_standardization_functions", lambda: functions)
    result = chemistry.analyze_structure(AnalyzeRequest(structure="CCO"))

    assert result.status.value == "valid"
    assert result.raw_input == "CCO"
    assert result.standardized_smiles is None
    assert [step.code for step in result.standardization_steps] == [
        "CLEANUP",
        "FRAGMENT_PARENT",
    ]
    assert [step.status for step in result.standardization_steps] == ["applied", "failed"]
    failed = result.standardization_steps[-1]
    assert failed.reason_code == "RDKIT_STANDARDIZATION_FAILURE"
    assert failed.reason
    assert all(prop.computed.value is None for prop in result.properties)
    assert all(prop.computed.status == ResultStatus.COMPUTATION_ERROR for prop in result.properties)
    assert all(prop.computed.reason_code == "STANDARDIZATION_FAILED" for prop in result.properties)
    assert all(prop.evidence.status == ResultStatus.NOT_APPLICABLE for prop in result.properties)


def test_structured_problem_type_controls_issue_code() -> None:
    class FakeValenceProblem:
        def GetType(self) -> str:
            return "AtomValenceException"

        def GetAtomIdx(self) -> int:
            return 7

        def Message(self) -> str:
            return "technical text without classification keywords"

    issue = chemistry._sanitization_issue(
        [FakeValenceProblem()],
        Chem.SanitizeFlags.SANITIZE_NONE,
    )
    assert issue.code == "IMPOSSIBLE_VALENCE"
    assert issue.location.atom_indices == [7]


def test_other_sanitization_flags_use_generic_stable_code() -> None:
    issue = chemistry._sanitization_issue(
        [],
        Chem.SanitizeFlags.SANITIZE_ADJUSTHS,
    )
    assert issue.code == "SANITIZATION_ERROR"
    assert issue.location.atom_indices == []
    assert issue.technical_detail == (
        f"RDKit sanitization flag: {int(Chem.SanitizeFlags.SANITIZE_ADJUSTHS)}"
    )


def test_missing_value_schema_requires_reason_and_available_requires_value() -> None:
    with pytest.raises(ValidationError):
        PropertyObservation(value=None, status=ResultStatus.NOT_AVAILABLE)
    with pytest.raises(ValidationError):
        PropertyObservation(
            value=None,
            status=ResultStatus.AVAILABLE,
            reason_code="INVALID_AVAILABLE_VALUE",
            reason="An available observation cannot be null.",
        )


def test_canonical_json_contract() -> None:
    left = {"unicode": "Å", "null": None, "nested": {"b": 2, "a": 1}}
    right = {"nested": {"a": 1, "b": 2}, "null": None, "unicode": "Å"}
    serialized = canonical_json(left)
    assert serialized == canonical_json(right)
    assert serialized == '{"nested":{"a":1,"b":2},"null":null,"unicode":"Å"}'
    with pytest.raises(ValueError):
        canonical_json({"not_finite": math.nan})


def test_configuration_hash_covers_chemistry_configuration() -> None:
    configuration = configuration_payload()
    assert {
        "pipeline",
        "ruleset",
        "chemistry_policy",
        "validation_policy",
        "validation",
        "input_normalization",
        "depiction",
        "standardization",
        "descriptors",
        "rdkit",
        "output_schema",
        "canonical_serialization",
        "snapshot",
    } == set(configuration)
    assert [step["code"] for step in configuration["standardization"]] == (
        STANDARDIZATION_ORDER
    )
    original_hash = configuration_sha256(configuration)

    changed_descriptor = deepcopy(configuration)
    changed_descriptor["descriptors"][1]["precision"] = 3
    assert configuration_sha256(changed_descriptor) != original_hash

    changed_validation = deepcopy(configuration)
    changed_validation["validation"]["unspecified_stereo_is_ambiguous"] = False
    assert configuration_sha256(changed_validation) != original_hash

    changed_normalization = deepcopy(configuration)
    changed_normalization["input_normalization"]["non_ring_aromatic_atom_case"][
        "enabled"
    ] = False
    assert configuration_sha256(changed_normalization) != original_hash

    changed_depiction = deepcopy(configuration)
    changed_depiction["depiction"]["atom_palette"] = "default"
    assert configuration_sha256(changed_depiction) != original_hash

    changed_schema = deepcopy(configuration)
    changed_schema["output_schema"] = "analysis-response-v2"
    assert configuration_sha256(changed_schema) != original_hash


def test_lowercase_non_ring_atoms_are_normalized_and_audited() -> None:
    result = chemistry.analyze_structure(AnalyzeRequest(structure="cco"))

    assert result.raw_input == "cco"
    assert result.status == MoleculeStatus.VALID
    assert result.canonical_smiles == "CCO"
    assert result.standardized_smiles == "CCO"
    assert [issue.code for issue in result.issues] == ["ATOM_CASE_NORMALIZED"]
    assert result.issues[0].severity == Severity.INFO
    assert result.issues[0].location.atom_indices == [0, 1, 2]
    assert result.standardization_steps[0].code == "NORMALIZE_NON_RING_ATOM_CASE"
    assert result.standardization_steps[0].before_smiles == "cco"
    assert result.standardization_steps[0].after_smiles == "CCO"


def test_aromatic_ring_case_is_never_uppercased() -> None:
    result = chemistry.analyze_structure(AnalyzeRequest(structure="c1ccccc1"))

    assert result.status == MoleculeStatus.VALID
    assert result.canonical_smiles == "c1ccccc1"
    assert all(issue.code != "ATOM_CASE_NORMALIZED" for issue in result.issues)
    assert all(
        step.code != "NORMALIZE_NON_RING_ATOM_CASE"
        for step in result.standardization_steps
    )


def test_only_non_ring_suffix_is_case_normalized() -> None:
    result = chemistry.analyze_structure(AnalyzeRequest(structure="c1ccccc1o"))

    assert result.status == MoleculeStatus.VALID
    assert result.canonical_smiles == "Oc1ccccc1"
    assert result.issues[0].location.atom_indices == [6]
    assert result.standardization_steps[0].after_smiles == "c1ccccc1O"


def test_case_normalization_does_not_hide_a_separate_valence_error() -> None:
    result = chemistry.analyze_structure(AnalyzeRequest(structure="o=c=n=c"))

    assert result.status == MoleculeStatus.INVALID
    assert result.canonical_smiles is None
    assert [issue.code for issue in result.issues] == [
        "IMPOSSIBLE_VALENCE",
        "ATOM_CASE_NORMALIZED",
    ]
    assert result.issues[0].location.atom_indices == [2]
    assert [step.code for step in result.standardization_steps] == [
        "NORMALIZE_NON_RING_ATOM_CASE"
    ]
