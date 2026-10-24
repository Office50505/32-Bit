"""Validate the scientifically reviewed Phase 2 gold dataset without application code."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

DATASET_DIR = Path(__file__).resolve().parent / "phase2_150_claims"
DATASET_PATH = DATASET_DIR / "claims.jsonl"
MANIFEST_PATH = DATASET_DIR / "manifest.json"

VERDICTS = {
    "SUPPORTED",
    "CONTRADICTED",
    "INSUFFICIENT_EVIDENCE",
    "OUT_OF_SCOPE",
}
DECISIVE_VERDICTS = {"SUPPORTED", "CONTRADICTED"}
OUT_OF_SCOPE_REASONS = {
    "CLINICAL_PREDICTION_OUT_OF_SCOPE",
    "SAFETY_PREDICTION_OUT_OF_SCOPE",
    "PERSONALIZED_ADVICE_OUT_OF_SCOPE",
    "FUTURE_EFFICACY_OUT_OF_SCOPE",
}
SHA256 = re.compile(r"^[a-f0-9]{64}$")


class DatasetValidationError(ValueError):
    """Raised when the gold dataset violates its frozen contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DatasetValidationError(message)


def load_dataset() -> tuple[list[dict[str, Any]], dict[str, Any], bytes]:
    dataset_bytes = DATASET_PATH.read_bytes()
    claims = [json.loads(line) for line in dataset_bytes.splitlines() if line.strip()]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return claims, manifest, dataset_bytes


def validate() -> dict[str, Any]:
    claims, manifest, dataset_bytes = load_dataset()
    _require(manifest["dataset_id"] == "provenancelab-phase2-150-gold-v1", "dataset ID drift")
    _require(manifest["status"] == "GOLD", "dataset status must be GOLD")
    _require(manifest["training_use"] == "PROHIBITED", "evaluation data cannot be training data")
    _require(len(claims) == manifest["claim_count"] == 150, "dataset must contain 150 claims")
    _require(
        hashlib.sha256(dataset_bytes).hexdigest() == manifest["dataset_sha256"],
        "dataset SHA-256 mismatch",
    )
    review = manifest["scientific_review"]
    _require(review["decision"] == "APPROVED_AS_GOLD", "gold review decision is missing")
    _require(bool(review["review_date"]), "gold review date is missing")
    _require(bool(review["reviewer_role"]), "gold reviewer role is missing")
    _require(
        review["approved_dataset_sha256"] == manifest["dataset_sha256"],
        "reviewed dataset SHA-256 does not match the frozen claim bytes",
    )

    expected_ids = [f"PL-EA-{index:03d}" for index in range(1, 151)]
    _require(
        [claim["claim_id"] for claim in claims] == expected_ids, "claim IDs are not sequential"
    )
    _require(len({claim["claim"] for claim in claims}) == 150, "claim texts must be unique")

    verdicts: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    difficulties: Counter[str] = Counter()
    folds: Counter[str] = Counter()
    leakage_folds: defaultdict[str, set[str]] = defaultdict(set)
    statement_count = 0
    compound_count = 0

    for claim in claims:
        _require(claim["split"] == "LOCKED_EVALUATION", f"{claim['claim_id']}: invalid split")
        _require(
            claim["annotation_status"] == "CANDIDATE",
            f"{claim['claim_id']}: original annotation provenance drifted",
        )
        _require(bool(claim["decision_basis_refs"]), f"{claim['claim_id']}: missing decision basis")
        _require(claim["fold"] in {"A", "B", "C", "D", "E"}, f"{claim['claim_id']}: invalid fold")
        _require(
            claim["difficulty"] in {"EASY", "MEDIUM", "HARD"},
            f"{claim['claim_id']}: invalid difficulty",
        )
        _require(bool(claim["expected_decomposition"]), f"{claim['claim_id']}: empty decomposition")
        _require(
            len(claim["expected_decomposition"]) <= 10,
            f"{claim['claim_id']}: decomposition exceeds API contract",
        )
        categories[claim["category"]] += 1
        difficulties[claim["difficulty"]] += 1
        folds[claim["fold"]] += 1
        leakage_folds[claim["leakage_group"]].add(claim["fold"])
        statement_count += len(claim["expected_decomposition"])
        compound_count += len(claim["expected_decomposition"]) > 1

        expected_statement_ids = [
            f"S{index}" for index in range(1, len(claim["expected_decomposition"]) + 1)
        ]
        _require(
            [item["statement_id"] for item in claim["expected_decomposition"]]
            == expected_statement_ids,
            f"{claim['claim_id']}: statement IDs are not ordered",
        )

        for item in claim["expected_decomposition"]:
            verdict = item["expected_verdict"]
            _require(verdict in VERDICTS, f"{claim['claim_id']}: unknown verdict {verdict}")
            _require(
                bool(item["rationale"]), f"{claim['claim_id']}/{item['statement_id']}: no rationale"
            )
            verdicts[verdict] += 1
            citations = item["expected_citations"]

            if verdict in DECISIVE_VERDICTS:
                _require(bool(citations), f"{claim['claim_id']}: decisive verdict without citation")
                required_stance = "SUPPORTS" if verdict == "SUPPORTED" else "CONTRADICTS"
                _require(
                    any(
                        citation["eligibility"] == "DECISIVE"
                        and citation["expected_stance"] == required_stance
                        and citation["retraction_status"] != "RETRACTED"
                        for citation in citations
                    ),
                    (
                        f"{claim['claim_id']}: decisive verdict lacks eligible "
                        f"{required_stance} evidence"
                    ),
                )
                if item["claim_type"] == "BIOLOGICAL_ACTIVITY":
                    _require(
                        any(
                            citation["basis"] == "EXPERIMENTAL"
                            and citation["eligibility"] == "DECISIVE"
                            for citation in citations
                        ),
                        f"{claim['claim_id']}: activity verdict lacks experimental evidence",
                    )
            elif verdict == "INSUFFICIENT_EVIDENCE":
                _require(
                    bool(item["expected_reason_codes"]),
                    f"{claim['claim_id']}: abstention lacks reason code",
                )
            else:
                _require(
                    set(item["expected_reason_codes"]) <= OUT_OF_SCOPE_REASONS
                    and len(item["expected_reason_codes"]) == 1,
                    f"{claim['claim_id']}: invalid out-of-scope reason",
                )
                _require(not citations, f"{claim['claim_id']}: out-of-scope verdict has citation")

            for citation in citations:
                _require(
                    SHA256.fullmatch(citation["raw_record_sha256"]) is not None, "bad citation hash"
                )
                _require(bool(citation["source_record_id"]), "missing source record ID")
                _require(bool(citation["snapshot_id"]), "missing snapshot ID")
                _require(bool(citation["locator"]), "missing citation locator")

    _require(statement_count == manifest["statement_count"] == 165, "statement count mismatch")
    _require(compound_count == manifest["compound_claim_count"] == 15, "compound count mismatch")
    _require(
        dict(sorted(verdicts.items())) == manifest["verdict_distribution"], "verdict counts drifted"
    )
    _require(
        verdicts
        == Counter(
            {
                "SUPPORTED": 45,
                "CONTRADICTED": 40,
                "INSUFFICIENT_EVIDENCE": 50,
                "OUT_OF_SCOPE": 30,
            }
        ),
        "verdict distribution is not the designed distribution",
    )
    _require(
        all(len(values) == 1 for values in leakage_folds.values()), "leakage group spans folds"
    )
    _require(set(folds) == {"A", "B", "C", "D", "E"}, "all five folds must be populated")
    _require(len(categories) >= 10, "category coverage is too narrow")
    _require(set(difficulties) == {"EASY", "MEDIUM", "HARD"}, "difficulty coverage is incomplete")

    for snapshot in manifest["source_snapshots"]:
        _require(
            SHA256.fullmatch(snapshot["source_sha256"]) is not None, "bad source snapshot hash"
        )
        _require(
            SHA256.fullmatch(snapshot["content_sha256"]) is not None, "bad content snapshot hash"
        )
    _require(
        len(manifest["pubchem_bundle"]["record_sha256s"]) == 18,
        "PubChem source bundle must contain 18 records",
    )

    return {
        "claim_count": len(claims),
        "statement_count": statement_count,
        "compound_claim_count": compound_count,
        "verdict_distribution": dict(sorted(verdicts.items())),
        "category_distribution": dict(sorted(categories.items())),
        "difficulty_distribution": dict(sorted(difficulties.items())),
        "fold_distribution": dict(sorted(folds.items())),
        "dataset_sha256": manifest["dataset_sha256"],
    }


def main() -> None:
    print(json.dumps(validate(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
