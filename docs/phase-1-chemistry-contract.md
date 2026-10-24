# ProvenanceLab Phase 1 chemistry contract

**Contract status:** proposed implementation contract; chemistry-owner approval is pending.  
**Toolkit baseline:** CPython 3.13.15 and RDKit 2026.09.1 in the project-local environment.  
**Authority:** Product Requirements Document v1.0, sections 7, 8, 10, and 12.

This document defines the behavior tested by the Phase 1 regression suite. Passing these tests proves consistency with this proposed contract in the pinned local environment; it does not constitute chemistry-owner approval or cross-version reproducibility.

## 1. Input, parsing, and classification

- `AnalyzeRequest.structure` preserves the exact submitted SMILES text. Chemistry transformations never replace `raw_input`.
- An absent, empty, or whitespace-only `structure` is a malformed API request and is rejected by request validation. It is not returned as a molecular-analysis result.
- A nonblank SMILES string that RDKit cannot parse returns HTTP 200 with molecule status `invalid`, issue code `SMILES_SYNTAX_ERROR`, no canonical/standardized structure, and blocked descriptor values.
- A parsed graph is sanitized before it can be `valid` or `ambiguous`. Depiction success is never used as proof of validity.
- A sanitization failure returns `invalid`. RDKit's structured chemistry problem type and sanitization flag determine the issue code; exception-message text is retained only as optional technical detail.
- A safely sanitized graph is `ambiguous` when RDKit reports an unspecified potential tetrahedral center or stereogenic double bond. It remains computable and is not relabeled invalid.
- Otherwise a safely sanitized graph is `valid`.

## 2. Stable issue contract

| Code | Severity | Trigger | Location policy |
|---|---|---|---|
| `SMILES_SYNTAX_ERROR` | error | RDKit cannot construct a graph from the nonblank input. | Empty unless a future parser API exposes a stable position. Parser log text is not parsed to invent a span. |
| `IMPOSSIBLE_VALENCE` | error | `AtomValenceException` or the RDKit property-sanitization flag. | Atom index only when provided by RDKit's structured problem object. |
| `AROMATICITY_ERROR` | error | `KekulizeException` or the RDKit kekulization flag. | All atom indices provided by RDKit's structured problem object. |
| `SANITIZATION_ERROR` | error | Another RDKit sanitization stage fails. | Structured atom indices when available; otherwise empty. |
| `UNSPECIFIED_STEREOCHEMISTRY` | warning | One or more RDKit potential tetrahedral centers or stereogenic double bonds are unspecified. | Atom and bond indices from `FindPotentialStereo`; no SMILES span is inferred. |
| `MULTIPLE_FRAGMENTS` | info | The sanitized input graph contains more than one disconnected component. | Empty; the issue applies to the molecular record rather than a single atom. |

Issue ordering is deterministic: blocking parse/sanitization issue alone for invalid inputs; unspecified stereochemistry before the multiple-fragment informational issue for computable inputs.

## 3. Stereochemistry policy

- Unspecified potential tetrahedral stereochemistry is ambiguous.
- An unspecified RDKit-stereogenic double bond is ambiguous under the proposed Phase 1 policy.
- Explicitly specified E/Z geometry remains valid when no other ambiguity exists.
- A stereochemical marker on an atom RDKit determines is not stereogenic does not itself create ambiguity. RDKit may remove that marker from the canonical representation.
- Phase 1 does not infer stereochemistry from names, depictions, biological context, or external evidence.

## 4. Standardization policy

Every computable molecule executes these operations in this fixed order:

1. `CLEANUP` - `rdMolStandardize.Cleanup`
2. `FRAGMENT_PARENT` - `rdMolStandardize.FragmentParent`
3. `UNCHARGE` - `rdMolStandardize.Uncharger().uncharge`
4. `CANONICAL_TAUTOMER` - `rdMolStandardize.TautomerEnumerator().Canonicalize`

Each successful step records its code, label, before/after isomeric SMILES, `changed` flag, and `applied` status. Parent selection does not delete the submitted multicomponent form from `raw_input` or `canonical_smiles`.

If a step raises an exception, that step is recorded as `failed` with stable reason code `RDKIT_STANDARDIZATION_FAILURE`; later steps do not run. The structure remains chemically valid/ambiguous, but `standardized_smiles` is absent and all computed properties receive `COMPUTATION_ERROR` with reason code `STANDARDIZATION_FAILED`. Evidence lookup is then `NOT_APPLICABLE`.

Parent choice, charge normalization, and tautomer choice are comparison policies. They are not claims about the only meaningful experimental form, physiological protonation state, or reaction equilibrium.

## 5. Descriptor contract

Descriptors are calculated on the successfully standardized structure. Values are computed predictions from RDKit, not experimental measurements.

| Key | RDKit definition | Unit | Serialization |
|---|---|---|---|
| `molecular_formula` | `rdMolDescriptors.CalcMolFormula` | none (text) | string |
| `molecular_weight` | `Descriptors.MolWt` | `g/mol` | rounded to 2 decimals |
| `exact_mass` | `Descriptors.ExactMolWt` | `Da` | rounded to 4 decimals |
| `logp` | `Crippen.MolLogP` | `unitless` | rounded to 2 decimals |
| `tpsa` | `rdMolDescriptors.CalcTPSA` | `A^2` | rounded to 2 decimals |
| `hbd` | `Lipinski.NumHDonors` | `count` | integer |
| `hba` | `Lipinski.NumHAcceptors` | `count` | integer |
| `rotatable_bonds` | `Lipinski.NumRotatableBonds` | `count` | integer |
| `ring_count` | `Lipinski.RingCount` | `count` | integer |
| `fraction_csp3` | `rdMolDescriptors.CalcFractionCSP3` | `unitless` | rounded to 2 decimals |

- Invalid inputs receive no computed values: status `INVALID_INPUT`, reason code `INVALID_STRUCTURE_BLOCKS_CALCULATION`, and an explanation.
- A descriptor exception is not converted to zero. It yields `COMPUTATION_ERROR`, reason code `RDKIT_DESCRIPTOR_FAILURE`, and an explanation.
- Ambiguous inputs remain computable. Their molecule-level warning and issue record carry the uncertainty; descriptor observations remain `AVAILABLE` because these ten descriptors do not select a stereoisomer in the current implementation.

## 6. Evidence and missing values

Phase 1 does not implement an evidence snapshot. For every valid or ambiguous standardized molecule, reference observations are null with:

- status `NOT_AVAILABLE`;
- reason code `REFERENCE_SNAPSHOT_NOT_CONFIGURED`;
- a human-readable explanation.

For invalid structures, evidence is null with `NOT_APPLICABLE` / `NO_VALID_STRUCTURE_FOR_LOOKUP`. For standardization failure, evidence is null with `NOT_APPLICABLE` / `NO_STANDARDIZED_STRUCTURE_FOR_LOOKUP`.

The response model requires every null observation to have both a nonempty stable reason code and explanation. An `AVAILABLE` observation cannot have a null value.

## 7. Canonical serialization and hashes

Canonical JSON uses Python's standard JSON encoder with:

- mapping keys sorted lexicographically;
- compact separators `,` and `:`;
- UTF-8 text with Unicode characters unescaped;
- explicit JSON `null` for present null fields;
- JSON numeric rendering after descriptor rounding;
- non-finite floating-point values rejected.

`input_sha256` hashes the complete Pydantic JSON-mode request, including the exact structure text and source metadata. Chemically equivalent but textually different requests intentionally have different input hashes.

`configuration_sha256` covers pipeline/ruleset and chemistry policy versions, validation classification policy, ordered standardization operations, descriptor methods/units/precision/tolerances, RDKit version, output schema version, serialization version, and snapshot identifier.

`output_sha256` covers the deterministic chemistry result payload used by the service: submitted label/input/source, classification, canonical and standardized structures, issues, standardization log, and computed/evidence observations. It excludes depiction SVG and the manifest itself. No wall-clock timestamp is currently present.

Three identical runs in one pinned environment must produce identical issue ordering, transformations, property serialization, and all three hashes. This is not evidence of identical behavior across RDKit or Python versions.

## 8. Approval boundary

All 31 corpus expectations are labelled `proposed`. No repository evidence shows chemistry-owner approval. Automated success therefore establishes an executable proposed baseline, while the release acceptance gate remains blocked until the decisions in `docs/phase-1-chemistry-decisions.md` are approved or amended and the corpus is rerun.
