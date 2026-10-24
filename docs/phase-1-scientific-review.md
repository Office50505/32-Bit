# Phase 1 scientific review packet

**Prepared:** 2026-10-24  
**Review state:** historical pre-approval audit; superseded by the project-owner approval recorded on 2026-10-25.

**Corpus state:** `approved` at corpus level as policy `phase1-approved.1`; per-case `proposed` values remain authorship provenance.
**Corpus SHA-256 at review preparation:** `dab3f3cab2267d105cdd6da98227824758dc5a6eb3c1ccca87279a1b838a35c3`

This packet audits the implemented proposal against the ProvenanceLab PRD and the checked-in tests. It is not an external scientific validation. The later project-owner approval accepts all 31 expectations as the Phase 1 product contract; statements about exact RDKit transformations remain version-pinned implementation behavior.

## 1. Authority and review boundary

Use these distinctions when reviewing the tables:

- **PRD requirement:** the project explicitly requires the behavior, such as blocking calculations for invalid input, the four-step standardization order, explicit missing-value reasons, three-run determinism, and chemistry-owner review of the 31 golden cases.
- **Established chemistry behavior:** basic structural reasoning such as an unclosed ring label being malformed, a carbon with five hydrogens violating the represented valence model, or identical substituents preventing a tetrahedral stereocenter. Exact toolkit classification and serialization still remain version-sensitive.
- **Proposed product policy:** choices such as RDKit parent selection, neutral comparison forms, canonical tautomer choice, warning granularity, units, rounding, hash boundaries, and stable issue priority.
- **Specialist decision:** a chemistry/cheminformatics reviewer must approve transformations and golden descriptor expectations. Automated tests and a software reviewer cannot supply that approval.

The repository and PRD identify a chemistry-owner role but do not name a person or contain a signature, credential, approval record, or approved corpus hash.

## 2. Verification performed

### Commands and results

| Check | Command | Result |
|---|---|---|
| Full backend suite | `.\.venv\Scripts\python.exe -m pytest .\backend\tests` | **47 passed**, 0 failed, 0 skipped, 0 errors; 1 `StarletteDeprecationWarning`; 4.09 s |
| Ruff | `.\.venv\Scripts\python.exe -m ruff check .\backend` | **All checks passed** |
| Phase 1 collection | `.\.venv\Scripts\python.exe -m pytest .\backend\tests\test_phase1_contract.py --collect-only -q` | **42 tests collected** |
| Corpus parameter collection | `.\.venv\Scripts\python.exe -m pytest .\backend\tests\test_phase1_contract.py::test_phase1_corpus_case_and_three_run_determinism --collect-only -vv` | **31 named case tests collected**, one for every corpus ID |

The warning comes from FastAPI's test client importing the deprecated `httpx` integration path. It is an environment/dependency compatibility warning, not a chemistry failure. Dependencies were not changed during this review.

### Corpus allocation

| PRD category | Required | Actual | Result |
|---|---:|---:|---|
| Syntax and ring-closure errors | 6 | 6 | Match |
| Valence, sanitization, and aromaticity | 6 | 6 | Match |
| Stereochemistry and geometry | 5 | 5 | Match |
| Salts, solvents, and disconnected fragments | 4 | 4 | Match |
| Charge and protonation | 3 | 3 | Match |
| Tautomer/equivalent forms | 3 | 3 | Match |
| Evidence and missing-value semantics | 4 | 4 | Match |
| **Total** | **31** | **31 distinct IDs** | **Match** |

The expected classifications are 14 valid, 4 ambiguous, and 13 invalid. The parametrized test calls the API three times per case, producing the reported 93 analyses. All IDs appear in pytest's collected node list, so no fixture row is orphaned.

## 3. Test quality and independence

The fixture expectations are static JSON authored separately from the service and are not calculated from the implementation at test runtime. They are therefore not mechanically tautological. They are not yet independent scientific goldens either: all are labeled `proposed`, no qualified reviewer or external reference calculation is recorded, and several exact expectations appear to capture the same installed RDKit behavior exercised by the service.

| Contract area | What the tests genuinely establish | What they do not yet establish |
|---|---|---|
| Corpus allocation | Exactly 31 unique IDs, required category counts, SMILES-only input, nonempty rationales, all `proposed`. | Scientific adequacy or representativeness of the selected examples. |
| Classification and canonical SMILES | Every case must match a static expected class and canonical string. | Independent correctness of those expected values. |
| Issue codes and severity | Exact ordered codes and severities are pinned for every case. | Multiple simultaneous chemistry problems, all generic sanitation paths, or cross-RDKit stability. |
| Issue locations | Exact atom/bond indices are checked when a fixture supplies a location. | Syntax cases and other rows without a fixture location only check explanatory fields for nonemptiness; they do not assert an empty or exact location. |
| Issue explanations | Title, summary, explanation, impact, and next step must be nonempty. | Exact stable wording, accuracy of each explanation, or readability. |
| Standardization | Four-step order, applied status, changed-step list, and final standardized SMILES are pinned for computable cases. | Exact expected `before_smiles` and `after_smiles` at each intermediate step; those fields are checked only for three-run equality. |
| Descriptor success/missingness | Ten observations exist per case; status and null/non-null behavior are checked; failures cannot silently become zero. | Numerical correctness for 17 of the 18 computable cases, per-case property identity/order, or diverse descriptor chemistry. |
| Descriptor golden values | All ten ethanol values and units are asserted in `EVID-001`. | Independent calculation, approved tolerances, and behavior for salts, charged forms, tautomers, rings, or stereochemical cases. |
| Evidence semantics | Every property has the expected no-snapshot or invalid-input status/reason, and nulls require a reason. | Evidence matching and tolerance behavior; no snapshot is configured by design. |
| Standardization failure | A controlled exception stops the pipeline and produces explicit error/missing states. | A natural, stable chemistry specimen that triggers this path. |
| Configuration hash | Required top-level sections are present; mutations to descriptor precision, ambiguity policy, and schema change the digest. | Mutation coverage for every chemistry-affecting field or proof that excluded fields cannot affect replay. |
| Determinism | Input, configuration, and output hashes are 64 hex characters and identical over three runs; issues, steps, and properties serialize identically. | Approved golden digests, cross-process/machine/version reproducibility, or detection of consistent but unintended output drift. |

Tests that are principally **presence checks** are issue narrative fields, non-null descriptor values outside `EVID-001`, and the number of property rows. Tests that are principally **determinism checks** are the three hashes, issue payloads, intermediate standardization records, and property payloads across the three calls. These are valuable regression checks, but they are not substitutes for scientific golden values.

## 4. Implementation map

The case tables use these implementation labels:

- **V — validation:** `backend/app/services/chemistry.py::_parse_and_validate` parses without sanitization, uses `Chem.DetectChemistryProblems` and `Chem.SanitizeMol`, then uses `Chem.FindPotentialStereo` and fragment counting.
- **I — issue mapping:** `backend/app/services/chemistry.py::_sanitization_issue` maps structured RDKit problem types and sanitization flags to stable codes and locations.
- **S — standardization:** `backend/app/services/chemistry.py::_standardize` executes the declared `CLEANUP`, `FRAGMENT_PARENT`, `UNCHARGE`, and `CANONICAL_TAUTOMER` functions in order.
- **D — descriptors:** `backend/app/services/chemistry.py::_properties` and `backend/app/core/chemistry_config.py` define calculators, units, rounding, and tolerances.
- **M — missing values/evidence:** `_invalid_properties`, `_standardization_failure_properties`, `evidence_for`, and model validators enforce explicit statuses and reasons.
- **H — provenance:** `backend/app/core/provenance.py` defines canonical JSON and the input, configuration, and output hash boundaries.

## 5. Case-by-case scientific review

### Syntax, ring closure, valence, sanitization, and aromaticity

| Case | Scientific rationale and authority | Proposed expected behavior | Relevant implementation | Unresolved review question |
|---|---|---|---|---|
| `SYNTAX-001` (`C1CC`) | The ring label is opened but never closed. Basic SMILES syntax; invalid-input blocking is PRD-required. | `invalid`; `SMILES_SYNTAX_ERROR`; no standardization or descriptors; evidence `NOT_APPLICABLE`. | V, M | Confirm this is a suitable stable golden parser example; parser prose is deliberately not pinned. |
| `SYNTAX-002` (`C(C`) | The branch parenthesis is unclosed. Basic syntax plus PRD blocking rule. | Same invalid contract as `SYNTAX-001`. | V, M | Confirm example coverage and empty-location policy. |
| `SYNTAX-003` (`C]`) | An unmatched closing bracket cannot form an atom expression. Basic syntax. | Same invalid contract. | V, M | Confirm example coverage and empty-location policy. |
| `SYNTAX-004` (`=CC`) | A bond token precedes the first atom. Basic syntax. | Same invalid contract. | V, M | Confirm example coverage and empty-location policy. |
| `SYNTAX-005` (`Q`) | `Q` is not a valid unbracketed element token. Basic syntax. | Same invalid contract. | V, M | Confirm the case is pedagogically useful and not overly toolkit-specific. |
| `SYNTAX-006` (`C-#C`) | Two incompatible bond tokens describe the same connection. Basic syntax. | Same invalid contract. | V, M | Confirm example coverage and empty-location policy. |
| `VAL-001` (`C[O](C)C`) | The represented neutral oxygen has three single bonds without a compatible charge. Established valence reasoning; exact toolkit code/location are proposed. | `invalid`; `IMPOSSIBLE_VALENCE`; atom index `[1]`; downstream work blocked. | V, I, M | Chemistry reviewer must confirm charge/valence interpretation and zero-based location. |
| `VAL-002` (`N(C)(C)(C)(C)C`) | Neutral nitrogen is represented with five single bonds. Established valence reasoning. | `invalid`; `IMPOSSIBLE_VALENCE`; atom `[0]`. | V, I, M | Confirm classification priority if RDKit reports more than one problem. |
| `VAL-003` (`[CH5]`) | Bracketed carbon is assigned five hydrogens. Established valence reasoning. | `invalid`; `IMPOSSIBLE_VALENCE`; atom `[0]`. | V, I, M | Confirm exact issue/location contract. |
| `VAL-004` (`c1cccc1`) | The all-aromatic five-carbon pattern cannot be kekulized by the pinned toolkit. Exact failure is toolkit behavior. | `invalid`; `AROMATICITY_ERROR`; atoms `[0,1,2,3,4]`. | V, I, M | Confirm that “aromaticity” is the desired public class rather than a narrower kekulization label. |
| `VAL-005` (`c1nccc1`) | This five-member aromatic pattern lacks a valid Kekulé assignment as written in the pinned toolkit. | `invalid`; `AROMATICITY_ERROR`; atoms `[0,1,2,3,4]`. | V, I, M | Qualified reviewer should validate the chemical explanation and highlighted atoms. |
| `VAL-006` (`c1cc1`) | Three aromatic carbons cannot be kekulized as written. | `invalid`; `AROMATICITY_ERROR`; atoms `[0,1,2]`. | V, I, M | Confirm the example and code priority across supported RDKit versions. |

### Stereochemistry and disconnected fragments

| Case | Scientific rationale and authority | Proposed expected behavior | Relevant implementation | Unresolved review question |
|---|---|---|---|---|
| `STEREO-001` (`CCC(O)C`) | 2-butanol has a potential tetrahedral center whose configuration is unspecified. Ambiguous-but-computable behavior is PRD-required; exact detection is toolkit-dependent. | `ambiguous`; warning at atom `[2]`; standardized `CCC(C)O`; descriptors available. | V, S, D | Approve molecule-level warning and continued descriptor computation. |
| `STEREO-002` (`CC(F)Cl`) | The central carbon has four different substituents but no assignment. | `ambiguous`; warning at atom `[1]`; standardized unchanged. | V, S, D | Same policy decision as `STEREO-001`; verify index and canonical spelling. |
| `STEREO-003` (`FC=CF`) | The double bond can have E/Z geometry but none is specified. | `ambiguous`; warning at bond `[1]`; standardized unchanged. | V, S, D | Approve potential-double-bond inclusion and bond-index precision. |
| `STEREO-004` (`C/C=C/C`) | Slash notation explicitly assigns double-bond geometry. | `valid`; no issue; isomeric canonical and standardized string retained. | V, S, D | Confirm one explicit geometry is enough for the Phase 1 corpus or require its counterpart. |
| `STEREO-005` (`F[C@](F)(Cl)Br`) | Two identical fluorine substituents mean the marked carbon is not stereogenic. | `valid`; no issue; marker removed in `FC(F)(Cl)Br`. | V, S, D | Decide whether silent marker removal is acceptable or warrants an ineffective-stereo warning. |
| `FRAG-001` (`CC(=O)[O-].[Na+]`) | Sodium acetate is multicomponent; the proposed comparison policy selects and neutralizes the organic parent. | `valid`; `MULTIPLE_FRAGMENTS`; `FRAGMENT_PARENT` and `UNCHARGE` change; final `CC(=O)O`. | V, S, D | Approve parent selection and neutral acetic-acid comparison identity; it is not the original material. |
| `FRAG-002` (`CCO.O`) | Water is treated as a removable small fragment while ethanol is the parent. | `valid`; `MULTIPLE_FRAGMENTS`; parent step changes; final `CCO`. | V, S, D | Approve solvent removal for this use case. |
| `FRAG-003` (`CC[NH3+].[Cl-]`) | Chloride is removed and ethylammonium is neutralized to ethylamine as the comparison parent. | `valid`; info issue; parent and uncharge steps change; final `CCN`. | V, S, D | Approve parent/charge transformation and comparison-only wording. |
| `FRAG-004` (`CCO.CCO`) | Equal duplicate fragments collapse deterministically to one parent under RDKit's rule. | `valid`; info issue; parent step changes; final `CCO`. | V, S, D | Decide whether duplicate collapse is scientifically and pedagogically acceptable or should be reported separately. |

### Charge, protonation, and tautomer policy

| Case | Scientific rationale and authority | Proposed expected behavior | Relevant implementation | Unresolved review question |
|---|---|---|---|---|
| `CHARGE-001` (`[NH4+]`) | The uncharger produces neutral ammonia as a comparison form. This is toolkit/product policy, not a physiological-state claim. | `valid`; no issue; `UNCHARGE` changes; final `N`. | S, D | Approve this mapping and whether charge normalization itself needs a visible issue. |
| `CHARGE-002` (`[O-]C(=O)C`) | Acetate maps to acetic acid under the uncharger. | `valid`; no issue; `UNCHARGE` changes; final `CC(=O)O`. | S, D | Approve the neutral comparison form and warning visibility. |
| `CHARGE-003` (`[NH3+]CC([O-])=O`) | Zwitterionic glycine maps to neutral glycine under the pinned uncharger. | `valid`; no issue; `UNCHARGE` changes; final `NCC(=O)O`. | S, D | Specialist must confirm that this comparison identity is appropriate and clearly not presented as the dominant physical state. |
| `TAUT-001` (`CC(=O)C`) | The keto form of acetone is already the pinned toolkit's canonical tautomer. | `valid`; no changed step; final canonical spelling `CC(C)=O`. | S, D | Confirm this as the reference member of the equivalence pair. |
| `TAUT-002` (`C=C(O)C`) | The enol canonicalizes to the same acetone keto comparison parent. | `valid`; `CANONICAL_TAUTOMER` changes; final `CC(C)=O`. | S, D | Approve equivalence and comparison-only interpretation. |
| `TAUT-003` (`Oc1ncccc1`) | 2-hydroxypyridine canonicalizes to the pyridone representation in pinned RDKit. | `valid`; tautomer step changes; final `O=c1cccc[nH]1`. | S, D | This chemically consequential equilibrium requires explicit specialist sign-off. |

### Evidence and missing-value semantics

| Case | Scientific rationale and authority | Proposed expected behavior | Relevant implementation | Unresolved review question |
|---|---|---|---|---|
| `EVID-001` (`CCO`) | A valid molecule can have computed values while reference values are unavailable because no snapshot is configured. PRD directly distinguishes unavailable evidence from zero or database miss. | `valid`; ten exact ethanol computed values; evidence `NOT_AVAILABLE` / `NO_SNAPSHOT_CONFIGURED`. | D, M, H | Independently verify all ten descriptor values, units, rounding, and formula-unit representation. |
| `EVID-002` (`C1CCC`) | Invalid syntax means no valid graph exists for either computation or evidence lookup. | `invalid`; syntax error; computed `INVALID_INPUT`; evidence `NOT_APPLICABLE`. | V, M | Confirm the status distinction and empty issue location. |
| `EVID-003` (`CC(O)F`) | A valid but stereochemically ambiguous graph remains computable; lack of snapshot remains a separate evidence state. | `ambiguous`; atom `[1]` warning; computed values `AVAILABLE`; evidence `NOT_AVAILABLE`. | V, S, D, M | Decide whether each computed property must carry `AMBIGUOUS_INPUT` or whether the molecule-level warning is sufficient. |
| `EVID-004` (`CC(=O)[O-].[K+]`) | A standardized salt parent still cannot have reference values without a configured snapshot; this is not `NO_REFERENCE_MATCH`. | `valid`; fragment issue; parent and uncharge changes; final `CC(=O)O`; evidence `NOT_AVAILABLE`. | V, S, D, M | Approve potassium-salt parent behavior and no-snapshot reason semantics. |

## 6. Scientific edge cases requiring careful review

1. **Stereo scope.** Only potential tetrahedral and double-bond stereo are detected. Axial, atropisomeric, coordination, enhanced stereo groups, and other stereochemical representations are not covered by the corpus or the stated policy.
2. **Ambiguity propagation.** The molecule is ambiguous while each successful descriptor is `AVAILABLE`. This is compatible with computing graph descriptors, but clients that ignore molecule status may miss the warning.
3. **Parent selection.** `FragmentParent` is a toolkit policy. It can collapse duplicate components and choose a parent that should not be described as the submitted substance.
4. **Neutralization.** Ammonium, acetate, ethylammonium, and zwitterionic glycine become neutral comparison forms. These transformations must not imply experimental protonation state, pH, or physiological prevalence.
5. **Tautomer collapse.** The acetone/enol and hydroxypyridine/pyridone pairs are useful but insufficient to establish a generally acceptable tautomer policy.
6. **Descriptor coverage.** Ethanol is the sole exact numerical golden. It does not exercise rings, ionic inputs before standardization, tautomers, hydrogen-bond edge cases, or nonzero rotatable/ring counts broadly enough for scientific approval.
7. **Precision and tolerances.** Python rounding happens before serialization. Proposed evidence tolerances are hashed but not executed. The owner must decide whether rounding is display-only or part of the scientific comparison value.
8. **Issue precision.** Atom/bond indices are zero-based and toolkit-derived. Syntax locations are empty. This is honest but must be explicit to API consumers.
9. **Failure behavior.** The fail-closed path is tested through a monkeypatch. No genuine stable molecule demonstrates an RDKit standardization failure, which is preferable to inventing one but limits corpus coverage.
10. **Version scope.** Exact canonical SMILES, aromaticity perception, tautomer ranking, descriptors, and hashes are pinned to RDKit `2026.09.1`. Three calls in one process do not prove cross-version reproducibility.

## 7. PRD, test, and implementation discrepancies

| Area | Finding | Required disposition |
|---|---|---|
| Scientific acceptance | PRD requires the 31 golden cases to be reviewed by the chemistry owner; the repository contains only proposed expectations. | Assign a qualified reviewer and record approval or amendments. |
| Descriptor golden depth | PRD acceptance is framed as scientific correctness, but only ethanol has exact descriptor values. Other computable cases assert presence. | Add owner-approved values for representative charged/standardized, tautomeric, aromatic/ring, and stereochemical cases, or explicitly approve the narrower Phase 1 gate. |
| Formula unit | PRD's descriptor table lists `Text` in the unit column for molecular formula; implementation returns a text value with JSON `unit: null`. | Product/API owner must approve `null` as “not a physical unit” or change the contract after review. |
| Algorithm context | PRD's property display contract calls for algorithm context. Methods are present in hashed configuration, but individual property observations do not expose a method/version field. | Decide whether manifest/configuration context is sufficient or add an API field in a separately authorized change. |
| Intermediate standardization | PRD calls for ordered before/after SMILES. The API emits them, but corpus tests do not pin their expected values step by step. | Add static expected intermediate values after chemistry approval if they are part of the golden contract. |
| Generic sanitization | A synthetic unit test checks `SANITIZATION_ERROR`; no corpus chemistry input exercises it. | Accept as branch-level coverage or add a justified stable case without manufacturing one. |
| Issue copy | Tests require narrative fields to be nonempty, not accurate or stable. | Chemistry/product review of copy is still required. |
| Hash goldens | PRD requires repeatability; current tests meet same-environment repeatability but do not pin approved digest values. | Pin selected digests after the contract is approved. |
| Configuration boundary | RDKit and chemistry settings are hashed. Python version is recorded in `tool_versions` but excluded from `configuration_sha256`; snapshot scope and depiction settings are also excluded. | Backend/product owner must confirm the replay boundary. The PRD explicitly names snapshot ID for the configuration hash, so scope exclusion is not automatically noncompliant. |
| Evidence tolerances | Tolerances are configured but cannot be acceptance-tested without reference values. | Chemistry lead approves now; execution tests follow only when frozen evidence is separately authorized. |
| Dependency warning | Full tests pass with a Starlette/httpx deprecation warning. | Track as maintenance; it does not block chemistry review and dependencies must not be changed merely to silence it. |

No concrete implementation defect was demonstrated during this review. The findings above are approval gaps, coverage limitations, or contract questions, so the chemistry service was not refactored.

## 8. Recommended approval procedure

1. **Assign reviewers.** Name a chemistry owner with computational chemistry or cheminformatics competence. Also assign a backend/product owner for API, missing-value, and hash-boundary decisions.
2. **Freeze the review target.** Record the Git commit or full working-tree patch, Python `3.13.15`, RDKit `2026.09.1`, chemistry policy `phase1-proposed.1`, and the corpus SHA-256 shown above. The current working tree is not clean, so a commit hash alone would not identify all reviewed content.
3. **Review PRD-direct behavior first.** Confirm invalid-input blocking, standardization order, explicit missing states, and three-run determinism without treating these confirmations as approval of individual chemistry transformations.
4. **Disposition every decision.** In `phase-1-chemistry-decisions.md`, mark each `P1-D01`–`P1-D17` approved, amended, or rejected, with reviewer, date, rationale, and any required changes.
5. **Review all 31 rows.** The chemistry owner should sign off each case or sign a cryptographic hash of the exact corpus plus a documented statement that every row was reviewed. Spot-checking is insufficient for the PRD's 31/31 gate.
6. **Independently verify descriptors.** Check methods, units, precision, rounding, and representative expected values without generating the goldens from the service under test. Approve the comparison tolerances even though evidence execution remains out of Phase 1 scope.
7. **Apply only approved amendments.** If review changes a proposed behavior, make the smallest implementation/fixture/test change, update policy version and decision record, then rerun the full backend suite and Ruff.
8. **Promote governance state last.** Change `proposed` to `approved` only after the signed/recorded decisions and reviewed corpus hash exist and all amended tests pass.

## 9. Post-approval status

- The project owner approved all 31 expectations on 2026-10-25 as policy `phase1-approved.1`.
- Explicit pairwise molecule-identity verdicts now remove the cross-input inference gap.
- Exact dependency versions, runtime fingerprints, stored requests, and recomputation-based replay verification now close the replay-verification gap.
- Independent external chemistry review is still advisable before scientific decision-making, but is not an open Phase 1 implementation item.

With the accepted corpus and passing verification suite, the declared Phase 1 product contract is complete.
