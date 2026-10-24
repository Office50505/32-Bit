# ProvenanceLab Phase 2 — 150-claim gold set

This directory contains the scientifically reviewed, checksum-frozen gold evaluation inputs and
expected atomic verdicts for the ProvenanceLab evidence assistant.

## Dataset shape

- 150 unique user claims
- 165 expected atomic statements
- 15 compound claims that require two-statement decomposition
- 45 `SUPPORTED`, 40 `CONTRADICTED`, 50 `INSUFFICIENT_EVIDENCE`, and 30 `OUT_OF_SCOPE`
- five deterministic folds (`A`–`E`) with each leakage group restricted to one fold
- easy, medium, and hard cases across structured properties, record-specific activity,
  stereochemistry, assay disagreement, retracted evidence, snapshot coverage, entity resolution,
  computed-property misuse, mechanism claims, and clinical/safety scope

The set is evaluation-only and must not be included in prompts used as demonstrations or in model
training data.

## Files

- `claims.jsonl` — one benchmark input per line, including expected decomposition, verdict,
  resolution state, stable reason codes, exact source-record citations, rationale, fold, and tags.
- `manifest.json` — counts, source snapshot identities, content hashes, PubChem record hashes, and
  the SHA-256 of the exact JSONL bytes.
- `../build_phase2_candidate.py` — deterministic gold-set builder from the frozen source records.
- `../validate_phase2_candidate.py` — standalone gold contract and checksum validator.

## Evidence boundary

Decisive biological-activity labels cite non-retracted ChEMBL experimental activity rows. Compound
property and identity labels cite checksum-frozen PubChem compound records. Abstentions cover
conflicting assays, retraction exclusion, missing coverage, unresolved or ambiguous identity,
computed-only evidence, and absent direct mechanism evidence. Out-of-scope labels cite the versioned
scope policy and deliberately contain no fabricated scientific citation.

Each claim has non-empty `decision_basis_refs`, even when the correct scientific-citation list is
empty. This keeps absence-of-evidence and policy decisions auditable without pretending that a
nonexistent assay record exists.

## Rebuild and validate

From the repository root:

```bash
python3 backend/evaluation/build_phase2_candidate.py
python3 backend/evaluation/validate_phase2_candidate.py
```

The builder refuses source checksum drift and missing sealed ChEMBL snapshots. The validator checks
the exact claim and statement counts, verdict distribution, citation eligibility, retraction rules,
reason-code requirements, fold isolation, and final dataset hash.

**Governance:** `GOLD`. The project owner scientifically reviewed and approved the frozen dataset
SHA-256 `b87d92f4814cdc51f91e6c6f3cafbb8238a700fbe0abb8bc5df4fead158d5356` on
2026-10-25. Per-row `annotation_status: CANDIDATE` values are intentionally retained as annotation
provenance; the signed manifest status is authoritative and no label bytes were silently changed.
