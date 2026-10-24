# ProvenanceLab Phase 1 external chemistry review matrix

**Package state:** prepared for external review; not scientifically approved.  
**Prepared:** 2026-10-24  
**Review status for every case and decision:** `PENDING`

This document is a self-contained review aid for a qualified chemistry or cheminformatics reviewer. It summarizes the proposed expectations and their test coverage so that the reviewer does not need to infer the contract from application code. Automated success demonstrates consistency with the proposed fixture; it does not validate the chemistry.

## 1. Review target identity

| Item | Recorded value | Qualification |
|---|---|---|
| Repository revision | `8804a32f9f56f950d639760985824b8b0174d353` on local `main` | Local branch was one commit ahead of `origin/main` when inspected. |
| Worktree before package creation | Clean | The prior `frontend/package-lock.json` change is already part of the recorded commit. It was not altered or discarded here. |
| Worktree after package creation | `docs/phase-1-review-matrix.md` is an uncommitted addition | The complete worktree is therefore not immutable or fully frozen. Do not identify the commit alone as containing this package file. |
| Corpus file | `backend/tests/fixtures/phase1_chemistry_corpus.json` | Corpus-level approval state is `proposed`; all 31 case states are `proposed`. |
| Corpus SHA-256 | `dab3f3cab2267d105cdd6da98227824758dc5a6eb3c1ccca87279a1b838a35c3` | Recalculated from the actual file on 2026-10-24. |
| Python | `3.13.15` | Recorded environment, not an independent chemistry authority. |
| RDKit | `2026.09.1` | Exact canonicalization, perception, descriptor values, and hashes are version-sensitive. |
| Pipeline version | `0.2.0` | Included in the configuration identity. |
| Ruleset version | `hm-01.2-proposed` | Proposed, not approved. |
| Chemistry policy | `phase1-proposed.1` | Proposed, not approved. |
| Validation policy | `rdkit-structured-problems-v1` | Proposed mapping of RDKit structured problems to stable issue codes. |
| Output schema | `analysis-response-v1` | Engineering contract awaiting owner approval. |
| Canonical serialization | `json-sort-keys-compact-utf8-finite-v1` | Engineering contract awaiting owner approval. |
| Evidence snapshot | `not-configured` | No Phase 2 data is included or reviewed. |
| Configuration SHA-256 | `c8cf04efdb24dc7030612ff08fe9aaca1d0378fe4aa34c761ce44cc8baca776b` | Calculated from the current configuration payload, including RDKit and snapshot ID. It is repeatability evidence, not scientific approval. |

### Corpus allocation

| PRD category | Cases |
|---|---:|
| SMILES syntax and ring closure | 6 |
| Valence, sanitization, and aromaticity | 6 |
| Stereochemistry and geometry | 5 |
| Salts, solvents, and fragments | 4 |
| Charges and protonation | 3 |
| Tautomers and equivalent forms | 3 |
| Evidence and missing semantics | 4 |
| **Total distinct case IDs** | **31** |

### Authority labels

- **PRD:** behavior expressly required by the Product Requirements Document, such as invalid-input blocking, explicit missing states, standardization order, and chemistry-owner review.
- **POLICY:** a proposed product or API choice that the PRD does not determine completely.
- **SCI:** a chemical or cheminformatics assumption requiring specialist confirmation.
- **RDKIT:** observed behavior of the pinned toolkit, not an independent scientific reference.

## 2. Automated coverage and weak-assertion legend

Every case is collected as a separately named parameter of `test_phase1_corpus_case_and_three_run_determinism`. The common test calls the API three times and checks input preservation, classification, canonical SMILES, ordered issue codes/severities, configured issue locations, standardization order and final result, ten property statuses and value presence/absence, evidence status/reason, and same-process repeatability.

Coverage labels used below:

- **CT:** common case contract described above.
- **LOC:** exact atom/bond location asserted because the fixture contains one.
- **EXACT-10:** exact values and units for all ten descriptors are asserted by the dedicated ethanol test.
- **MISS:** model and response tests require explicit reason codes and explanations for null values.
- **FAIL:** controlled descriptor/standardization failure tests exercise fail-closed behavior.

Weak-assertion labels used below:

- **W1 - presence only:** outside `EVID-001`, computable cases assert descriptor status and non-null values, not numeric correctness.
- **W2 - narrative nonempty:** issue title, summary, explanation, impact, and next step are required to be nonempty, but their wording and scientific accuracy are not golden assertions.
- **W3 - repeatability only:** hashes and serialized issues/steps/properties must repeat over three calls, but no approved expected digest is pinned.
- **W4 - intermediate steps not golden:** step order, changed-step list, and final standardized SMILES are asserted; exact expected before/after SMILES for each intermediate step are not stored in the fixture.
- **W5 - location incomplete:** exact issue locations are checked only where the fixture supplies them. Syntax cases do not pin an empty or character-span location.
- **W6 - no independent oracle:** fixture expectations were not documented as independently calculated or externally reviewed.
- **W7 - evidence path absent:** no frozen snapshot is configured, so matching, tolerance boundaries, conflicts, and source provenance are not exercised.

### Missing-value profiles

- **M-INVALID:** ten computed observations are `INVALID_INPUT` with null values and reason `INVALID_STRUCTURE_BLOCKS_CALCULATION`; evidence is `NOT_APPLICABLE` with `NO_VALID_STRUCTURE_FOR_LOOKUP`.
- **M-NOSNAPSHOT:** ten computed observations are `AVAILABLE`; evidence is null `NOT_AVAILABLE` with `NO_SNAPSHOT_CONFIGURED`. This means unavailable evidence, not a database miss.

## 3. Case-by-case review matrix

### 3.1 SMILES syntax and ring closure

| Case / category | Input | Expected classification / issues | Standardization | Descriptor and missing-value expectations | Rationale and authority | Automated coverage | Known limitations | Review |
|---|---|---|---|---|---|---|---|---|
| `SYNTAX-001` / `syntax_ring_closure` | `C1CC` | `invalid`; `SMILES_SYNTAX_ERROR` | Not run; standardized SMILES null | `M-INVALID` | Ring label is opened but not closed. **PRD:** invalid graphs block computation. **SCI:** basic SMILES grammar. | CT, MISS | W2, W3, W5, W6 | `PENDING` |
| `SYNTAX-002` / `syntax_ring_closure` | `C(C` | `invalid`; `SMILES_SYNTAX_ERROR` | Not run; standardized SMILES null | `M-INVALID` | Branch parenthesis is unclosed. **PRD + SCI.** | CT, MISS | W2, W3, W5, W6 | `PENDING` |
| `SYNTAX-003` / `syntax_ring_closure` | `C]` | `invalid`; `SMILES_SYNTAX_ERROR` | Not run; standardized SMILES null | `M-INVALID` | Closing bracket has no matching atom-expression opener. **PRD + SCI.** | CT, MISS | W2, W3, W5, W6 | `PENDING` |
| `SYNTAX-004` / `syntax_ring_closure` | `=CC` | `invalid`; `SMILES_SYNTAX_ERROR` | Not run; standardized SMILES null | `M-INVALID` | Bond token precedes the first atom. **PRD + SCI.** | CT, MISS | W2, W3, W5, W6 | `PENDING` |
| `SYNTAX-005` / `syntax_ring_closure` | `Q` | `invalid`; `SMILES_SYNTAX_ERROR` | Not run; standardized SMILES null | `M-INVALID` | `Q` is not a valid unbracketed SMILES atom token. **PRD + SCI.** | CT, MISS | W2, W3, W5, W6 | `PENDING` |
| `SYNTAX-006` / `syntax_ring_closure` | `C-#C` | `invalid`; `SMILES_SYNTAX_ERROR` | Not run; standardized SMILES null | `M-INVALID` | Two incompatible bond tokens describe one connection. **PRD + SCI.** | CT, MISS | W2, W3, W5, W6 | `PENDING` |

### 3.2 Valence, sanitization, and aromaticity

| Case / category | Input | Expected classification / issues | Standardization | Descriptor and missing-value expectations | Rationale and authority | Automated coverage | Known limitations | Review |
|---|---|---|---|---|---|---|---|---|
| `VAL-001` / `valence_sanitization_aromaticity` | `C[O](C)C` | `invalid`; `IMPOSSIBLE_VALENCE`; atom `[1]` | Not run | `M-INVALID` | Represented neutral oxygen has three single bonds without compatible charge. **PRD:** issue class and blocking. **SCI/RDKIT:** exact interpretation and index. | CT, LOC, MISS | W2, W3, W6 | `PENDING` |
| `VAL-002` / `valence_sanitization_aromaticity` | `N(C)(C)(C)(C)C` | `invalid`; `IMPOSSIBLE_VALENCE`; atom `[0]` | Not run | `M-INVALID` | Neutral nitrogen is represented with five single bonds. **PRD + SCI/RDKIT.** | CT, LOC, MISS | W2, W3, W6; multi-problem priority not exercised by this row | `PENDING` |
| `VAL-003` / `valence_sanitization_aromaticity` | `[CH5]` | `invalid`; `IMPOSSIBLE_VALENCE`; atom `[0]` | Not run | `M-INVALID` | Bracketed carbon is assigned five hydrogens. **PRD + SCI/RDKIT.** | CT, LOC, MISS | W2, W3, W6 | `PENDING` |
| `VAL-004` / `valence_sanitization_aromaticity` | `c1cccc1` | `invalid`; `AROMATICITY_ERROR`; atoms `[0,1,2,3,4]` | Not run | `M-INVALID` | Pinned RDKit cannot kekulize the all-aromatic five-carbon pattern. **PRD:** stable class. **POLICY/RDKIT:** public aromaticity label and indices. | CT, LOC, MISS | W2, W3, W6; exact failure may drift by toolkit version | `PENDING` |
| `VAL-005` / `valence_sanitization_aromaticity` | `c1nccc1` | `invalid`; `AROMATICITY_ERROR`; atoms `[0,1,2,3,4]` | Not run | `M-INVALID` | Pinned RDKit cannot assign a valid Kekule form as written. **PRD + SCI/RDKIT.** | CT, LOC, MISS | W2, W3, W6; explanation needs specialist review | `PENDING` |
| `VAL-006` / `valence_sanitization_aromaticity` | `c1cc1` | `invalid`; `AROMATICITY_ERROR`; atoms `[0,1,2]` | Not run | `M-INVALID` | Three aromatic carbons cannot be kekulized as written. **PRD + SCI/RDKIT.** | CT, LOC, MISS | W2, W3, W6; no natural corpus example for generic `SANITIZATION_ERROR` | `PENDING` |

### 3.3 Stereochemistry and geometry

| Case / category | Input | Expected classification / issues | Standardization | Descriptor and missing-value expectations | Rationale and authority | Automated coverage | Known limitations | Review |
|---|---|---|---|---|---|---|---|---|
| `STEREO-001` / `stereochemistry_geometry` | `CCC(O)C` | `ambiguous`; `UNSPECIFIED_STEREOCHEMISTRY`; atom `[2]` | All four steps applied; none marked changed; final `CCC(C)O` | `M-NOSNAPSHOT`; numeric descriptor values not pinned | 2-butanol has an unassigned potential tetrahedral center. **PRD:** ambiguous input remains computable with warning. **SCI/RDKIT:** center perception. | CT, LOC, MISS | W1, W2, W3, W4, W6, W7; properties do not carry `AMBIGUOUS_INPUT` | `PENDING` |
| `STEREO-002` / `stereochemistry_geometry` | `CC(F)Cl` | `ambiguous`; `UNSPECIFIED_STEREOCHEMISTRY`; atom `[1]` | Four steps; unchanged; final `CC(F)Cl` | `M-NOSNAPSHOT`; presence only | Central carbon has four different substituents without assignment. **PRD + SCI/RDKIT.** | CT, LOC, MISS | W1-W4, W6, W7 | `PENDING` |
| `STEREO-003` / `stereochemistry_geometry` | `FC=CF` | `ambiguous`; `UNSPECIFIED_STEREOCHEMISTRY`; bond `[1]` | Four steps; unchanged; final `FC=CF` | `M-NOSNAPSHOT`; presence only | Potential E/Z double-bond geometry is unspecified. **PRD + SCI/RDKIT.** | CT, LOC, MISS | W1-W4, W6, W7; no explicit Z counterpart in corpus | `PENDING` |
| `STEREO-004` / `stereochemistry_geometry` | `C/C=C/C` | `valid`; no issue | Four steps; unchanged; final `C/C=C/C` | `M-NOSNAPSHOT`; presence only | Slash notation specifies geometry. **SCI:** explicit geometry. **POLICY/RDKIT:** exact canonical spelling and validity contract. | CT, MISS | W1-W4, W6, W7; only one explicit geometry represented | `PENDING` |
| `STEREO-005` / `stereochemistry_geometry` | `F[C@](F)(Cl)Br` | `valid`; no issue | Four steps; no changed step recorded; final `FC(F)(Cl)Br` | `M-NOSNAPSHOT`; presence only | Identical fluorine substituents prevent a tetrahedral stereocenter. **SCI:** non-stereogenic. **POLICY:** silently remove ineffective marker. | CT, MISS | W1-W4, W6, W7; PRD does not decide whether a warning is needed | `PENDING` |

### 3.4 Salts, solvents, and disconnected fragments

| Case / category | Input | Expected classification / issues | Standardization | Descriptor and missing-value expectations | Rationale and authority | Automated coverage | Known limitations | Review |
|---|---|---|---|---|---|---|---|---|
| `FRAG-001` / `salts_solvents_fragments` | `CC(=O)[O-].[Na+]` | `valid`; `MULTIPLE_FRAGMENTS` | Changed `FRAGMENT_PARENT`, `UNCHARGE`; final `CC(=O)O` | `M-NOSNAPSHOT`; presence only | Organic parent selection and neutralization produce acetic acid comparison form. **PRD:** ordered auditable steps. **POLICY/SCI/RDKIT:** selected parent and neutral form. | CT, MISS | W1-W4, W6, W7; result is not the submitted material or physiological state | `PENDING` |
| `FRAG-002` / `salts_solvents_fragments` | `CCO.O` | `valid`; `MULTIPLE_FRAGMENTS` | Changed `FRAGMENT_PARENT`; final `CCO` | `M-NOSNAPSHOT`; presence only | Water is removed while ethanol is retained as comparison parent. **PRD + POLICY/RDKIT.** | CT, MISS | W1-W4, W6, W7; solvent-removal policy needs approval | `PENDING` |
| `FRAG-003` / `salts_solvents_fragments` | `CC[NH3+].[Cl-]` | `valid`; `MULTIPLE_FRAGMENTS` | Changed `FRAGMENT_PARENT`, `UNCHARGE`; final `CCN` | `M-NOSNAPSHOT`; presence only | Chloride removal plus neutralization yields ethylamine comparison form. **PRD + POLICY/SCI/RDKIT.** | CT, MISS | W1-W4, W6, W7; identity and protonation implications | `PENDING` |
| `FRAG-004` / `salts_solvents_fragments` | `CCO.CCO` | `valid`; `MULTIPLE_FRAGMENTS` | Changed `FRAGMENT_PARENT`; final `CCO` | `M-NOSNAPSHOT`; presence only | Duplicate equal fragments collapse to one parent. **POLICY/RDKIT:** deterministic toolkit behavior, not an explicit PRD outcome. | CT, MISS | W1-W4, W6, W7; multiplicity is lost in comparison parent | `PENDING` |

### 3.5 Charge and protonation

| Case / category | Input | Expected classification / issues | Standardization | Descriptor and missing-value expectations | Rationale and authority | Automated coverage | Known limitations | Review |
|---|---|---|---|---|---|---|---|---|
| `CHARGE-001` / `charge_protonation` | `[NH4+]` | `valid`; no issue | Changed `UNCHARGE`; final `N` | `M-NOSNAPSHOT`; presence only | RDKit Uncharger maps ammonium to neutral ammonia comparison form. **PRD:** uncharge step. **POLICY/SCI/RDKIT:** exact mapping and no warning. | CT, MISS | W1-W4, W6, W7; must not imply dominant physical state | `PENDING` |
| `CHARGE-002` / `charge_protonation` | `[O-]C(=O)C` | `valid`; no issue | Changed `UNCHARGE`; final `CC(=O)O` | `M-NOSNAPSHOT`; presence only | Acetate maps to acetic acid comparison form. **PRD + POLICY/SCI/RDKIT.** | CT, MISS | W1-W4, W6, W7; pH and counterion context absent | `PENDING` |
| `CHARGE-003` / `charge_protonation` | `[NH3+]CC([O-])=O` | `valid`; no issue | Changed `UNCHARGE`; final `NCC(=O)O` | `M-NOSNAPSHOT`; presence only | Glycine zwitterion maps to neutral glycine comparison form. **PRD + POLICY/SCI/RDKIT.** | CT, MISS | W1-W4, W6, W7; scientifically consequential state collapse | `PENDING` |

### 3.6 Tautomers and equivalent forms

| Case / category | Input | Expected classification / issues | Standardization | Descriptor and missing-value expectations | Rationale and authority | Automated coverage | Known limitations | Review |
|---|---|---|---|---|---|---|---|---|
| `TAUT-001` / `tautomer_equivalent_form` | `CC(=O)C` | `valid`; no issue | No changed step; final canonical spelling `CC(C)=O` | `M-NOSNAPSHOT`; presence only | Keto acetone is already the pinned toolkit's canonical tautomer. **PRD:** canonical tautomer step. **POLICY/RDKIT:** ranking result. | CT, MISS | W1-W4, W6, W7 | `PENDING` |
| `TAUT-002` / `tautomer_equivalent_form` | `C=C(O)C` | `valid`; no issue | Changed `CANONICAL_TAUTOMER`; final `CC(C)=O` | `M-NOSNAPSHOT`; presence only | Enol maps to the acetone keto comparison parent. **PRD + POLICY/SCI/RDKIT.** | CT, MISS | W1-W4, W6, W7; equivalence may be context-sensitive | `PENDING` |
| `TAUT-003` / `tautomer_equivalent_form` | `Oc1ncccc1` | `valid`; no issue | Changed `CANONICAL_TAUTOMER`; final `O=c1cccc[nH]1` | `M-NOSNAPSHOT`; presence only | 2-hydroxypyridine maps to the pyridone tautomer in pinned RDKit. **PRD + POLICY/SCI/RDKIT.** | CT, MISS | W1-W4, W6, W7; equilibrium and context are not represented | `PENDING` |

### 3.7 Evidence and missing-value semantics

| Case / category | Input | Expected classification / issues | Standardization | Descriptor and missing-value expectations | Rationale and authority | Automated coverage | Known limitations | Review |
|---|---|---|---|---|---|---|---|---|
| `EVID-001` / `evidence_missing_semantics` | `CCO` | `valid`; no issue | Four steps; unchanged; final `CCO` | `M-NOSNAPSHOT`; exact ten-value ethanol vector listed in Section 4 | A valid molecule has computed values but unavailable evidence when no snapshot exists. **PRD:** explicit no-snapshot state. **RDKIT:** descriptor numbers. | CT, EXACT-10, MISS | W2-W4, W6, W7; exact values come from the same toolkit contract and are not independently checked | `PENDING` |
| `EVID-002` / `evidence_missing_semantics` | `C1CCC` | `invalid`; `SMILES_SYNTAX_ERROR` | Not run | `M-INVALID` | Evidence is not applicable when no valid graph exists. **PRD:** invalid versus unavailable distinction. **SCI:** unclosed ring syntax. | CT, MISS | W2, W3, W5, W6 | `PENDING` |
| `EVID-003` / `evidence_missing_semantics` | `CC(O)F` | `ambiguous`; `UNSPECIFIED_STEREOCHEMISTRY`; atom `[1]` | Four steps; unchanged; final `CC(O)F` | `M-NOSNAPSHOT`; descriptor values present, not exact | Ambiguity and no-snapshot evidence are independent states. **PRD:** compute with warning and expose missing reason. **POLICY:** properties remain `AVAILABLE`. | CT, LOC, MISS | W1-W4, W6, W7; property-level ambiguity propagation unresolved | `PENDING` |
| `EVID-004` / `evidence_missing_semantics` | `CC(=O)[O-].[K+]` | `valid`; `MULTIPLE_FRAGMENTS` | Changed `FRAGMENT_PARENT`, `UNCHARGE`; final `CC(=O)O` | `M-NOSNAPSHOT`; descriptor values present, not exact | Standardized salt parent still has unavailable evidence, not `NO_REFERENCE_MATCH`. **PRD:** no-snapshot semantics. **POLICY/SCI/RDKIT:** parent mapping. | CT, MISS | W1-W4, W6, W7 | `PENDING` |

## 4. Descriptor review matrix

Implementation calculates descriptors on the fully standardized comparison parent. For floating-point results, `backend/app/services/chemistry.py` applies Python `round(value, precision)` before serialization and hashing. Integer calculators remain integers. The only numerical vector currently asserted is ethanol (`EVID-001`), and its source is the proposed test expectation produced for the pinned RDKit contract, not an independent database or laboratory reference.

| Descriptor | Actual RDKit function | Chemical definition for review | Unit | Precision / tolerance | Current internal value, if any | Expected limitations | Independent check |
|---|---|---|---|---|---|---|---|
| Molecular formula | `rdMolDescriptors.CalcMolFormula` | Elemental composition string for the standardized molecular graph, including implied hydrogens according to RDKit. | No physical unit; implementation returns `unit: null`. PRD table says `Text`, which needs API interpretation. | No rounding; exact string equality proposed. | Ethanol: `C2H6O`; source: `EVID-001` test expectation only. | Depends on standardized charge/tautomer/fragment state and toolkit hydrogen handling. | `NEEDS REVIEW` |
| Molecular weight | `Descriptors.MolWt` | RDKit average molecular weight calculated from its atomic-weight table for the standardized graph. | `g/mol` | Rounded to 2 decimals; proposed tolerance `0.02`. | Ethanol: `46.07`; internal proposed golden only. | Not monoisotopic mass; atomic-weight conventions and standardized form matter. | `NEEDS REVIEW` |
| Exact mass | `Descriptors.ExactMolWt` | Sum of RDKit exact/monoisotopic atomic masses for the represented isotopic composition. | `Da` | Rounded to 4 decimals; proposed tolerance `0.001`. | Ethanol: `46.0419`; internal proposed golden only. | Default isotope assumptions, explicit isotopes, adducts, and ion state affect interpretation. | `NEEDS REVIEW` |
| LogP | `Crippen.MolLogP` | Wildman-Crippen atom-fragment estimate of octanol/water partition coefficient for the standardized structure. | Unitless | Rounded to 2 decimals; proposed tolerance `0.15`. | Ethanol: `-0.0`; internal proposed golden only. | Predictive model, not an experimental measurement; protonation, tautomer, and standardization matter. Negative-zero serialization needs approval. | `NEEDS REVIEW` |
| Topological polar surface area | `rdMolDescriptors.CalcTPSA` | Fragment-based topological estimate of polar surface area from the 2D molecular graph. | `A^2` in current API; reviewer should confirm preferred Angstrom-squared notation. | Rounded to 2 decimals; proposed tolerance `0.1`. | Ethanol: `20.23`; internal proposed golden only. | Topological approximation, not conformational solvent-accessible surface area. | `NEEDS REVIEW` |
| Hydrogen-bond donors | `Lipinski.NumHDonors` | Count of donor sites according to RDKit's Lipinski definition. | `count` | Integer; proposed exact equality. | Ethanol: `1`; internal proposed golden only. | Rule-set definitions and protonation/tautomer state determine counts. | `NEEDS REVIEW` |
| Hydrogen-bond acceptors | `Lipinski.NumHAcceptors` | Count of acceptor sites according to RDKit's Lipinski definition. | `count` | Integer; proposed exact equality. | Ethanol: `1`; internal proposed golden only. | Rule-set definitions, formal charge, and tautomer state determine counts. | `NEEDS REVIEW` |
| Rotatable bonds | `Lipinski.NumRotatableBonds` | Count of rotatable bonds under RDKit's default Lipinski implementation. | `count` | Integer; proposed exact equality. | Ethanol: `0`; internal proposed golden only. | Alternative strict/non-strict definitions can differ; ring, terminal, and amide treatment must be accepted explicitly. | `NEEDS REVIEW` |
| Ring count | `Lipinski.RingCount` | RDKit ring count for the standardized graph under its ring-perception behavior. | `count` | Integer; proposed exact equality. | Ethanol: `0`; internal proposed golden only. | Fused, bridged, and aromatic systems can expose definition differences not covered by ethanol. | `NEEDS REVIEW` |
| Fraction Csp3 | `rdMolDescriptors.CalcFractionCSP3` | Fraction of carbon atoms perceived as sp3-hybridized by RDKit. | Unitless | Rounded to 2 decimals; proposed tolerance `0.01`. | Ethanol: `1.0`; internal proposed golden only. | Sensitive to carbon count, aromaticity, and hybridization perception; zero-carbon behavior is not covered. | `NEEDS REVIEW` |

### Descriptor approval requested

The qualified reviewer should independently verify at least one chemically diverse set beyond ethanol: a ring-containing structure, hydrogen-bond edge case, charged input before standardization, fragment-parent case, and tautomer pair. The reviewer must approve definitions, units, rounding, negative-zero handling, and tolerances. No external reference values have been inserted into this package.

## 5. Seventeen-decision reviewer checklist

An approval is valid only if the reviewer examines the actual fixture expectations and relevant implementation behavior. Checking a box because 47 automated tests pass is not scientific review.

| ID | Question | Proposed default | Principal risk | Exact approval or amendment required | Status |
|---|---|---|---|---|---|
| `P1-D01` | Which malformed SMILES are invalid and blocking? | Syntax parse failure returns `invalid`/`SMILES_SYNTAX_ERROR`; no downstream chemistry. | Parser-specific examples or messaging mistaken for universal chemistry. | Approve all seven referenced syntax cases, blocking behavior, and non-golden parser prose, or amend specific rows. | `PENDING` |
| `P1-D02` | How are valence/aromaticity/sanitization failures prioritized? | Structured valence, then kekulization/aromaticity, then generic sanitization. | Wrong stable code when several problems coexist; toolkit drift. | Approve code priority, six cases, and generic fallback coverage, or specify revised priority/cases. | `PENDING` |
| `P1-D03` | Does unassigned tetrahedral stereo make input ambiguous but computable? | `ambiguous` plus atom warning; graph descriptors remain available. | Stereochemical uncertainty may be hidden at property level. | Approve classification, locations, continued calculation, and stated limitation, or require property-level ambiguity. | `PENDING` |
| `P1-D04` | How is unspecified versus explicit E/Z handled? | Potential unassigned E/Z is ambiguous; explicit slash geometry is valid. | Incorrect identity/evidence matching or incomplete explicit-geometry coverage. | Approve the two fixture outcomes and coverage scope, or add/amend explicit geometries. | `PENDING` |
| `P1-D05` | What happens to a marker on a non-stereogenic center? | Valid input; marker silently disappears during canonicalization. | Authoring error may be concealed. | Approve silent normalization or define a stable ineffective-stereo warning and tests. | `PENDING` |
| `P1-D06` | What issue-location precision is public? | Zero-based RDKit atom/bond indices; empty location when structured data is unavailable. | False precision, consumer indexing mistakes, cross-version drift. | Approve zero-based semantics and empty syntax locations, or specify another stable representation. | `PENDING` |
| `P1-D07` | Which disconnected fragment is the comparison parent? | RDKit `FragmentParent` in the mandated order. | Parent may misrepresent the submitted material; duplicates collapse. | Approve each fragment case and comparison-only wording, or amend parent-selection policy. | `PENDING` |
| `P1-D08` | Which charged forms map to neutral comparison forms? | RDKit `Uncharger` maps listed ammonium, acetate, ethylammonium, and glycine forms. | Protonation or physiological claims; altered identity/descriptors. | Approve each transformation and limitation, or list forms that must retain charge. | `PENDING` |
| `P1-D09` | Which tautomer represents comparison identity? | RDKit canonical tautomer; listed enol and hydroxypyridine mappings. | Contextually meaningful forms may be collapsed. | Approve all three exact mappings as comparison policy, or amend equivalence/ranking rules. | `PENDING` |
| `P1-D10` | Are descriptor methods, units, precision, and rounding correct? | Ten functions and serialization rules in Section 4. | Scientifically wrong labels/values; hash drift; false precision. | Independently verify representative values and approve every row, including `unit: null`, `A^2`, and `-0.0`, or provide amendments. | `PENDING` |
| `P1-D11` | What comparison tolerances are scientifically acceptable? | Configured absolute tolerances; exact equality for text/counts. | False agreement or conflict in later evidence comparison. | Approve every tolerance and comparison convention before evidence activation, or provide replacements and boundary cases. | `PENDING` |
| `P1-D12` | How does molecule ambiguity propagate to properties? | Molecule is ambiguous; successful graph descriptors remain `AVAILABLE`. | Property-only clients may omit the warning. | Approve molecule-level warning as sufficient or require `AMBIGUOUS_INPUT` at property/comparison level. | `PENDING` |
| `P1-D13` | What happens when standardization fails? | Stop, log stable failure reason, omit standardized identity, return computation errors. | Partial results could appear authoritative; natural failure coverage is absent. | Approve fail-closed behavior and synthetic coverage, or define additional stable real cases. | `PENDING` |
| `P1-D14` | What exact request and serialization are hashed? | Exact nonblank input plus source metadata; sorted compact finite UTF-8 JSON. | Semantically equivalent inputs intentionally hash differently; byte contract may surprise clients. | Backend/product owner approves byte-level rules and whitespace behavior or supplies revised canonicalization. | `PENDING` |
| `P1-D15` | What belongs in `configuration_sha256`? | Chemistry/pipeline/schema/serialization/RDKit/snapshot ID included; Python, snapshot scope, depiction excluded. | Behavior-affecting state may be omitted from replay identity. | Approve every included/excluded field and add mutation coverage for accepted boundary, or amend payload. | `PENDING` |
| `P1-D16` | What belongs in `output_sha256`? | Deterministic chemistry payload included; depiction SVG and manifest excluded. | Consistent unintended drift is not caught without golden digests. | Approve boundary and pin reviewed digests for valid, ambiguous, and invalid cases, or revise fields. | `PENDING` |
| `P1-D17` | What evidence promotes the corpus from proposed to approved? | Named qualified review, case/decision disposition, corpus hash, policy version, and passing rerun. | Tests may be misrepresented as scientific sign-off. | Record reviewer identity/role/date, reviewed revision plus package diff, exact corpus hash, all decisions, exceptions, and rerun results before changing any approval state. | `PENDING` |

## 6. Reviewer sign-off procedure

1. Verify the target identifiers in Section 1, including the corpus hash and the uncommitted package file.
2. Review every row in Section 3 against the actual expected classification, issue, location, transformation, descriptor behavior, and missing-value behavior.
3. Review every descriptor in Section 4 using an independent calculation or authoritative method knowledge. Record sources separately; do not treat the implementation output as its own validation.
4. Disposition every decision in Section 5 as `APPROVED`, `APPROVED WITH LIMITATION`, `AMEND`, or `REJECT`, with rationale.
5. If amendments are required, change implementation and fixtures only in a separately authorized task, increment relevant policy/version identifiers, and rerun the full backend suite and Ruff.
6. Record reviewer identity, role, relevant competence, date, exact revision plus uncommitted review-package hash/diff, corpus SHA-256, decision dispositions, and exceptions.
7. Change corpus states from `proposed` only after the above record exists and all approved amendments pass.

## 7. Current review limitations and preparation gaps

- No qualified chemistry reviewer, identity, signature, or approval is recorded.
- All 31 cases remain `PENDING` and all machine-readable expectations remain `proposed`.
- Descriptor values are independently unverified; only ethanol has exact internal golden assertions.
- Evidence comparison is intentionally not testable because no snapshot is configured; Phase 2 is out of scope.
- Same-process three-run determinism does not prove cross-machine or cross-version reproducibility.
- The review package file is uncommitted, so the Git revision alone does not identify the full package.
- Poppler rendering was unavailable in the current shell; relevant PRD pages were text-extracted for this Markdown package. The source PDF itself was not modified.

**Package conclusion:** ready to send to a qualified external chemistry or cheminformatics reviewer. Scientific approval has not been obtained.
