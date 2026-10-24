from __future__ import annotations

import sys
from pathlib import Path

EVALUATION_DIR = Path(__file__).resolve().parents[1] / "evaluation"
sys.path.insert(0, str(EVALUATION_DIR))

from validate_phase2_candidate import validate  # noqa: E402


def test_phase2_gold_dataset_contract() -> None:
    summary = validate()

    assert summary["claim_count"] == 150
    assert summary["statement_count"] == 165
    assert summary["compound_claim_count"] == 15
    assert summary["verdict_distribution"] == {
        "CONTRADICTED": 40,
        "INSUFFICIENT_EVIDENCE": 50,
        "OUT_OF_SCOPE": 30,
        "SUPPORTED": 45,
    }
    assert len(summary["dataset_sha256"]) == 64
