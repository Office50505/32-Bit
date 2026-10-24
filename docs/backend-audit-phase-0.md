# ProvenanceLab Backend Audit - Phase 0

**Audit date:** 24 October 2026 (Asia/Kolkata)  
**Scope:** read-only audit of the existing repository. No application source, dependency, environment, database, deployment setting, or generated run data was changed.  
**PRD reviewed:** `output/pdf/ProvenanceLab_Product_Requirements_Document_v1.0.pdf`, version 1.0.  
**Working tree at start:** clean (`git status --short` produced no entries).  

## 1. Executive summary

This repository contains a compact, credible direct-SMILES prototype, not the full backend described by the target PRD. Its source code implements FastAPI startup, a health route, single and batch analysis, RDKit parsing/sanitization, a four-step standardization flow, ten RDKit descriptors, explanatory issue records, an explicit no-snapshot evidence response, and deterministic-looking SHA-256 manifest generation. The implementation is concentrated in six backend modules and five API-level tests.

The installed environment could not execute the backend: the available host interpreter is Python 3.14.3, while the project declares Python `>=3.11,<3.14`, and that interpreter has no FastAPI, RDKit, pytest, or Ruff. Therefore no endpoint, chemistry result, hash, or test is runtime-verified in this audit. Static observations below are deliberately identified as such.

The highest risks are scientific-contract incompleteness and absence of regression evidence, rather than a detected source-code crash:

1. The required 31-case chemistry corpus does not exist. Five tests cover only aspirin, impossible valence, one unspecified-stereochemistry example, repeat-hash equality, and source metadata.
2. Frozen evidence is an intentional stub. There is no snapshot manifest, ingest/verify/index/activate code, matcher, coverage logic, or snapshot readiness signal.
3. Runs are not persisted and cannot be retrieved or replayed. The frontend only keeps drafts and photo previews in browser session storage.
4. The configuration hash omits the descriptor methods, units, tolerances, standardization implementation settings, and full snapshot provenance required by the PRD. The output hash is calculated from a reduced internal payload, not the full API response.
5. The batch API accepts **1 through 100** requests, whereas the PRD requires batches of at least 2 through 100. There is no per-item isolation, timing limit, or runtime test.

**Readiness decision:** the backend is **not ready for the next broad implementation phase or release gate**. It is ready for a tightly scoped Phase 1 chemistry-contract task: establish the approved 31-case golden corpus and test the existing validation/standardization/descriptor behavior in the pinned supported environment before adding evidence or persistence.

## 2. Audit method and limitations

I inspected all tracked backend source, backend tests, root operational documentation/configuration, the available design document, the PRD PDF text, the relevant frontend API/session code needed to establish real source/export/run behavior, the tracked-file inventory, and Git status. No existing `docs/backend-audit-phase-0.md` was present before this file was created.

This audit distinguishes:

- **Observed:** directly present in source/configuration or a command result.
- **Static inference:** behavior indicated by code but not executed in this environment.
- **Unverified:** cannot be claimed without a supported runtime, configured snapshot, persistence store, or test.

The PRD PDF was text-inspected with `pdftotext`. `pdfinfo` is not installed, so PDF metadata/page count could not be independently queried; this does not affect the reviewed PRD content. No network, dataset, API, installation, or environment mutation was performed.

## 3. Actual backend architecture and data flow

```text
Browser UI (frontend/src/api/analysis.ts)
  | JSON POST /api/analyze or /api/analyze/batch
  v
FastAPI app (backend/app/main.py)
  | includes /api router; development-only CORS origins
  v
Routes (backend/app/api/routes.py)
  | AnalyzeRequest / BatchAnalyzeRequest Pydantic validation
  v
analyze_structure (backend/app/services/chemistry.py)
  |-- _parse_and_validate: RDKit parse unsanitized -> sanitize -> stereo/fragments
  |-- _standardize: Cleanup -> FragmentParent -> Uncharger -> Canonicalize tautomer
  |-- _properties: ten RDKit calculations -> evidence_for for every property
  |-- _depict: optional SVG depiction
  |-- create_manifest
  v
AnalyzeResponse (backend/app/models/analysis.py)
  | manifest fields from backend/app/core/provenance.py
  `-- evidence is always NOT_AVAILABLE from backend/app/services/evidence.py

No persistence repository, database model, migration, file-store, snapshot package, report generator, replay service, background worker, Docker/deployment configuration, or readiness service exists in the tracked tree.
```

The frontend establishes two important boundaries that the backend does not implement:

- `frontend/src/utils/photoSource.ts` validates PNG/JPEG/WebP and a 2 MB limit, hashes the file in the browser, and stores its data URL in `sessionStorage`. The backend receives metadata only through `SourceMetadata`; it never receives or stores the file.
- `frontend/src/pages/ResultsPage.tsx` creates a client-side JSON download from the current `results` array. It is not a persistent backend run export, and no PDF is generated.

## 4. Backend capability inventory

| # | Capability | Status | Evidence | Audit finding / missing evidence |
|---:|---|---|---|---|
| 1 | Application startup and health endpoint | IMPLEMENTED BUT NOT VERIFIED | `backend/app/main.py: app`; `backend/app/api/routes.py: health` | A FastAPI app includes `/api`; health returns service, pipeline, ruleset, and RDKit versions. Import/startup and `GET` response could not run. It always reports `ok`; it does not expose snapshot readiness. |
| 2 | Single-molecule analysis endpoint | IMPLEMENTED BUT NOT VERIFIED | `routes.py: analyze`; `models/analysis.py: AnalyzeRequest/AnalyzeResponse`; `chemistry.py: analyze_structure` | Route and typed models exist. Runtime response/error behavior is unverified. |
| 3 | Batch analysis endpoint and actual limits | PARTIALLY IMPLEMENTED | `routes.py: analyze_batch`; `models/analysis.py: BatchAnalyzeRequest` | List validation is `min_length=1, max_length=100`, so actual accepted size is 1-100, not PRD 2-100. It loops synchronously with no per-item failure isolation, concurrency control, or performance test. |
| 4 | Input preservation and request validation | PARTIALLY IMPLEMENTED | `AnalyzeRequest`, `SourceMetadata`; `chemistry.py: analyze_structure`; `provenance.py: create_manifest` | Raw `structure` and source metadata are returned and request JSON is hashed. SMILES has 1-20,000-character and label 200-character limits. No file content is registered/stored; no source type allow-list, source-size upper bound, or request-body limit exists in the backend. |
| 5 | RDKit parsing and sanitization | IMPLEMENTED BUT NOT VERIFIED | `chemistry.py: _parse_and_validate` | Uses `Chem.MolFromSmiles(..., sanitize=False)` then `Chem.SanitizeMol`; maps parse and sanitation failures to issue records. Requires execution against supported pinned RDKit. |
| 6 | Stable issue codes and issue explanations | PARTIALLY IMPLEMENTED | `models/analysis.py: ValidationIssue`; `chemistry.py: _invalid_issue`, `_parse_and_validate` | Codes for syntax, valence, aromaticity, generic sanitization, stereochemistry, and fragments are emitted with explanatory fields. Codes are free strings, syntax positions are never populated, and no complete issue-code regression suite exists. |
| 7 | Ambiguity and stereochemistry handling | PARTIALLY IMPLEMENTED | `chemistry.py: Chem.FindMolChiralCenters` branch | Unassigned tetrahedral chiral centers become warning `UNSPECIFIED_STEREOCHEMISTRY`, making the molecule ambiguous. No explicit double-bond/geometry ambiguity handling is visible, and no test proves behavior across the PRD category. |
| 8 | Standardization rule ordering | IMPLEMENTED BUT NOT VERIFIED | `chemistry.py: _standardize` | Source order is exactly Cleanup, FragmentParent, Uncharger, Canonical tautomer, matching PRD section 8.1. No golden test verifies execution or effects in the declared RDKit version. |
| 9 | Before/after transformation records | IMPLEMENTED BUT NOT VERIFIED | `models/analysis.py: StandardizationStep`; `chemistry.py: apply_step` | Each of four operations records code, label, before/after isomeric SMILES, and `changed`. Runtime behavior is not verified. |
| 10 | All ten descriptor definitions and units | PARTIALLY IMPLEMENTED | `chemistry.py: PROPERTY_SPECS`, `_properties` | All ten named PRD descriptors and the expected RDKit calculator families are present. Molecular-weight/exact-mass/TPSA units are supplied; formula and unitless values use `None` rather than the PRD's explicit `Text`/`Unitless` vocabulary. No algorithm context is returned and no execution/golden verification is available. |
| 11 | Invalid-input descriptor blocking | IMPLEMENTED BUT NOT VERIFIED | `chemistry.py: _invalid_properties`, invalid branch in `analyze_structure`; `tests/test_analysis.py: test_impossible_valence_is_not_computed` | Static branch returns ten `INVALID_INPUT` computed observations and `NOT_APPLICABLE` evidence observations with reasons. A test exists but could not run. |
| 12 | Missing-value statuses and reason codes | PARTIALLY IMPLEMENTED | `ResultStatus`, `PropertyObservation`; `_invalid_properties`; `evidence.py: evidence_for` | Enum covers the PRD status names and current null observations include reason code/reason. The model does not enforce reason fields whenever `value is None`; `AMBIGUOUS_INPUT`, `NOT_COMPUTABLE`, coverage/no-match, and conflict behaviors are not exercised by a real evidence path. |
| 13 | Frozen evidence snapshot ingestion and verification | NOT IMPLEMENTED | `evidence.py: evidence_for`; absence of snapshot/ingest modules and data | The only implementation always returns `NOT_AVAILABLE` / `REFERENCE_SNAPSHOT_NOT_CONFIGURED`. No manifests, checksums, ingestion, schema checks, indexes, activation, retirement, or immutable data store exist. |
| 14 | Evidence matching, coverage, and conflict detection | PARTIALLY IMPLEMENTED | `chemistry.py: _comparison_status`, `_properties`; `evidence.py` | Generic comparison/tolerance code exists but cannot reach available evidence with current provider. There is no identity matcher, coverage declaration, property provenance, conflict test, or real source record. |
| 15 | Input, configuration, and output SHA-256 hashes | IMPLEMENTED BUT NOT VERIFIED | `provenance.py: canonical_json`, `sha256_text`, `create_manifest`; test hash equality | Canonical JSON sorts keys and uses compact separators. Runtime determinism has one test but it could not execute. Completeness limitations are documented in section 7. |
| 16 | Manifest completeness and deterministic serialization | PARTIALLY IMPLEMENTED | `RunManifest`, `ToolVersions`; `provenance.py` | Core fields exist and JSON canonicalization is explicit. Configuration omits descriptor definitions/tolerances and standardization settings; tools omit evidence/ingestion/OCR/editor versions; snapshot has only placeholder ID/scope; source hashes/decision log are not manifest fields. |
| 17 | Persistent run creation and retrieval | NOT IMPLEMENTED | No `/api/runs` route/repository/database; `ResultsPage.tsx`; `runDraft.ts` | No backend storage or retrieval. UI uses session storage only. |
| 18 | Replay from original input and output-hash verification | NOT IMPLEMENTED | No replay route/service/tests; `README.md` roadmap | No preserved run input/configuration/environment resolver, re-execution, mismatch diagnostics, or dependency-blocking response exists. |
| 19 | Structure-source registration and file ingestion | NOT IMPLEMENTED | `SourceMetadata` only; no `/api/sources`; `photoSource.ts` | Backend accepts metadata passed by client but receives no upload bytes and has no supported MOL/SDF/CSV/PDF/image ingestion. |
| 20 | JSON export and PDF report generation | PARTIALLY IMPLEMENTED | `ResultsPage.tsx: downloadRun`; absence of backend export/report module | A browser can download active results as JSON. There is no persistent API export or PDF generator/report route. |
| 21 | Automated regression tests and 31-case corpus | NOT IMPLEMENTED | `backend/tests/test_analysis.py`; repository-wide corpus search; PRD section 12 | There are five tests, not a 31-case corpus, and no fixtures/golden data or expected hashes. Tests were blocked by missing packages. |
| 22 | Security, request limits, error handling, readiness checks | PARTIALLY IMPLEMENTED | `AnalyzeRequest`, `SourceMetadata`; `main.py` CORS; chemistry exception handling | Pydantic field bounds, source hash pattern, selected CORS origins, sanitation exception mapping, and descriptor exception mapping exist. Missing backend file validation/isolation, body/rate/timeout controls, structured global error handling, logging/observability, auth/privacy/retention, production CORS/deployment, performance/readiness checks, and snapshot readiness. |

## 5. API surface audit

### Existing routes

| Method | Endpoint | Implementation | Request schema | Response schema | Current static behavior | Error handling | Relevant tests | PRD status |
|---|---|---|---|---|---|---|---|---|
| GET | `/api/health` | `backend/app/api/routes.py: health` | none | `HealthResponse` | Returns literal `status: "ok"`, service name, and pipeline/ruleset/RDKit version values. | Default FastAPI behavior only; no readiness/dependency assessment. | None. | Current endpoint exists; target snapshot-readiness extension is absent. |
| POST | `/api/analyze` | `routes.py: analyze` -> `chemistry.py: analyze_structure` | `AnalyzeRequest` | `AnalyzeResponse` | Parses/sanitizes one SMILES; returns valid/ambiguous/invalid result, properties, explicit unconfigured evidence, SVG when depiction succeeds, and manifest. | Pydantic request violations use FastAPI defaults (normally 422, unexecuted); parse/sanitize and descriptor exceptions are represented; unhandled standardization/manifest faults would be 500. | All five tests call this route. | Current endpoint exists, static functionality is substantial but runtime unverified. |
| POST | `/api/analyze/batch` | `routes.py: analyze_batch` | `BatchAnalyzeRequest` | `BatchAnalyzeResponse` | Runs `analyze_structure` sequentially for each list item. Actual schema limit is 1-100. | Pydantic list/item errors default to FastAPI; no per-item exception isolation or aggregate run manifest. | None. Frontend contains a caller in `frontend/src/api/analysis.ts`. | Exists, but partially compliant because minimum should be 2 and reliability/performance are unverified. |

### Target routes that do not exist

| Target endpoint | Observed status | Evidence |
|---|---|---|
| POST `/api/sources` | NOT IMPLEMENTED | `routes.py` declares only three routes; no source storage/ingestion module. |
| POST `/api/runs` | NOT IMPLEMENTED | No route, persistence model, repository, or database config. |
| GET `/api/runs/{id}` | NOT IMPLEMENTED | No route or persistent record. |
| POST `/api/runs/{id}/replay` | NOT IMPLEMENTED | No route, replay service, environment/snapshot resolver, or verification test. |
| GET `/api/snapshots` | NOT IMPLEMENTED | No snapshot registry/data directory/service. |

The PRD correctly calls the first three routes “Current” and the remaining routes “Target.” Do not infer target routes from the frontend route parameter: `ResultsPage.tsx` reads an `analysis_id` from the client route but rejects it when it does not match current session results; it does not fetch a backend run.

## 6. PRD compliance matrix

| PRD requirement | Status | Implementation evidence | Gap / verification evidence needed |
|---|---|---|---|
| FR-001 preserve exact submitted structure and source metadata | PARTIAL | `AnalyzeRequest.structure`, `AnalyzeResponse.raw_input`, source echo, request hash | Backend preserves request text, but cannot preserve uploaded source artifact; runtime test of whitespace/exact payload absent. |
| FR-002 supported inputs: MVP SMILES; target structure/files/drawing/image | PARTIAL | `input_type: Literal["smiles"]` | SMILES only; no backend files/drawing/PDF/image handling. |
| FR-003 confirmation of extracted/drawn candidates | NOT IMPLEMENTED | No candidate schemas/decision log | UI confirmation is not a backend candidate lifecycle. |
| FR-004 syntax validation | IMPLEMENTED BUT NOT VERIFIED | `_parse_and_validate` with `SMILES_SYNTAX_ERROR` | Add syntax/ring corpus and runtime test. |
| FR-005 chemical validation | IMPLEMENTED BUT NOT VERIFIED | `Chem.SanitizeMol`; valence/aromaticity/sanitization mapping | Add coverage for all failure classes and location behavior. |
| FR-006 ambiguity detection | PARTIAL | chiral-center detection | Double-bond/geometry and category tests absent. |
| FR-007 issue explanation | PARTIAL | `ValidationIssue` fields and constructors | Stable typed taxonomy, parser spans/bond locations, and all-path tests absent. |
| FR-008 depiction | PARTIAL | `_depict` | Valid and partial depiction attempted; it silently returns `None` on error and has no depiction tests. |
| FR-009 fixed standardization policy | IMPLEMENTED BUT NOT VERIFIED | `_standardize` order | Pin/verify behavior against approved corpus and capture configuration details. |
| FR-010 transformation log | IMPLEMENTED BUT NOT VERIFIED | `StandardizationStep`; `apply_step` | Runtime/golden test needed. |
| FR-011 agreed descriptor set only for valid inputs | PARTIAL | `PROPERTY_SPECS`; `_invalid_properties` | Ten implementations are present; unit contract, algorithm context, approved tolerances, and golden verification are incomplete. |
| FR-012 immutable frozen evidence only | NOT IMPLEMENTED | `evidence_for` stub | No snapshot source at all; the stub does correctly avoid live data/fabrication. |
| FR-013 null semantics | PARTIAL | status enum and current reason messages | Schema does not require reason for all nulls; state paths untested. |
| FR-014 computed/reference comparison | PARTIAL | `_comparison_status` | No evidence value/provenance/match/coverage path exists. |
| FR-015 batch run 2-100 | PARTIAL | `BatchAnalyzeRequest` uses 1-100 | Fix minimum and add reliability/performance semantics/tests. |
| FR-016 manifest hashes/versions/snapshot | PARTIAL | `create_manifest`, `RunManifest` | Hash canonicalization exists; configuration/snapshot/tool detail incomplete. |
| FR-017 machine JSON + target PDF | PARTIAL | client `downloadRun` | JSON only client-side/current-session; no PDF. |
| FR-018 replay | NOT IMPLEMENTED | none | Requires persistence, immutable dependency resolver, rerun, and hash compare. |
| FR-019 snapshot administration | NOT IMPLEMENTED | none | Requires import/verify/index/activate/retire lifecycle. |
| FR-020 health/readiness | PARTIAL | `health` | Service/tool versions only; no snapshot readiness or operational checks. |

## 7. Scientific correctness audit

### Observed conforming behavior (static)

- **Original vs. transformed form:** `analyze_structure` keeps `request.structure` in `raw_input`; `_standardize` begins from a copy of the sanitized molecule and logs each before/after step. `FRAGMENT_PARENT` is explicit, so the original multicomponent notation remains available in `raw_input` and the first log entry.
- **Syntax versus chemical invalidity:** parser failure produces `SMILES_SYNTAX_ERROR`; sanitation failures are classified as valence, aromaticity, or generic sanitization. Invalid inputs take `_invalid_properties`, rather than calculating descriptors.
- **Ambiguity distinct from invalidity:** unspecific chiral centers remain a sanitized molecule, add a warning, and result in `MoleculeStatus.AMBIGUOUS`; the invalid branch is separate.
- **Depiction is not the validator:** parsing/sanitization determines molecule status before `_depict` is called. A failed depiction returns `None`, not a valid classification.
- **Declared standardization order:** code order matches PRD: CLEANUP, FRAGMENT_PARENT, UNCHARGE, CANONICAL_TAUTOMER.
- **No fabricated/live reference value:** `evidence_for` always returns a clear missing reference state and contains no networking implementation.

### Risks and questions requiring chemistry-owner review

| Topic | Evidence / concern | Required verification |
|---|---|---|
| Validation taxonomy | String matching on exception text (`"valence"`, `"kekul"`) determines code. RDKit exception text/version behavior may vary. | Pin compatible RDKit and approve 31 expected code/location outcomes. |
| Ambiguity coverage | Only `FindMolChiralCenters` is used. No explicit E/Z or broader geometry ambiguity detection is visible. | Specify supported ambiguity scope and prove it with the five PRD stereo/geometry cases. |
| Issue locations | Syntax failures have no spans; sanitization atom index is only provided when exception exposes `GetAtomIdx`; bond locations are never populated. | Define deterministic location expectations and test them. |
| Fragment semantics | `MULTIPLE_FRAGMENTS` has INFO severity, so molecule remains valid unless another warning exists; descriptors/evidence run on the parent while raw form is retained. | Confirm this is the intended product classification and test salts/solvents/fragments. |
| Descriptor units/context | `None` denotes formula/unitless fields, despite the PRD's named units; no method/version/context appears per descriptor. | Chemistry owner should approve response contract, method labels, units, precision, and tolerances. |
| Ambiguous-property status | Ambiguous molecules calculate properties with `AVAILABLE`, relying on molecule-level status/issue for warning. `AMBIGUOUS_INPUT` exists but is not emitted. | Decide whether the property contract requires a per-property ambiguity indication. |
| Transformation provenance | Logs molecule-level isomeric SMILES, but no RDKit standardizer settings/version/configuration details are hashed. | Capture approved standardization configuration in the versioned configuration contract. |

## 8. Reproducibility audit

`backend/app/core/provenance.py` uses `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` then SHA-256 UTF-8 encoding. That is an appropriate canonicalization pattern for JSON-compatible request/response payloads and avoids dictionary-order differences.

| Hash | Actual input | Strength | Gap against PRD |
|---|---|---|---|
| `input_sha256` | `request.model_dump(mode="json")` | Includes structure, label, `input_type`, and supplied source metadata. | Does not prove preservation/hash of actual uploaded bytes because backend never receives/stores them. No test for canonical/request edge cases. |
| `configuration_sha256` | only `{pipeline, ruleset, snapshot}` | Stable and concise. | Omits descriptor keys/methods/units/tolerances, standardization configuration, RDKit/Python version, snapshot scope/release/checksum, evidence adapter version, and any future source/OCR/editor dependency. This does not meet PRD 10.1 completeness. |
| `output_sha256` | internal `response_payload` assembled in `analyze_structure` | Avoids volatile timestamps; contains label/raw input/status/canonical/standardized forms/issues/steps/properties/source. | Excludes `depiction_svg`, `analysis_id`, and the manifest/tool-version data returned by `AnalyzeResponse`. Whether depiction should be excluded is not documented; the code does not explicitly define the payload as a canonical output contract. |

`analysis_id` is deterministically derived from the first eight hex characters of the input hash and first four of the configuration hash (`PL-...-...`). This is stable but not a persisted run identifier and uses a truncated 48-bit visible prefix; it should not be treated as globally collision-proof storage identity without an explicit collision policy.

There is no replay implementation. Consequently, the audit cannot verify original-input re-execution, immutable snapshot/environment resolution, output-hash equality, mismatch diagnostics, or blocked-dependency semantics required by PRD 10.2.

## 9. Test baseline and 31-case corpus

### Commands executed

| Command | Exit code | Result |
|---|---:|---|
| `git status --short` | 0 | No output; clean tracked working tree at audit start. |
| `python --version` | 0 | Python 3.14.3 host interpreter. |
| `python -c "import fastapi, pydantic, rdkit; ..."` | 1 | `ModuleNotFoundError: No module named 'fastapi'`. |
| `Push-Location backend; python -m pytest` | 1 | `No module named pytest`. |
| `python -m ruff check backend` | 1 | `No module named ruff`. |

No `.venv` or `backend/.venv` directory exists. `backend/pyproject.toml` supports Python `>=3.11,<3.14`, so the host Python 3.14.3 is unsupported even if dependencies were installed. Per audit constraints, no packages were installed and no tests/lint were bypassed.

### Existing backend tests

`backend/tests/test_analysis.py` contains **five** tests:

1. aspirin valid status, molecular weight 180.16, and unconfigured evidence state;
2. impossible valence blocks all computed properties;
3. unassigned stereochemistry becomes ambiguous;
4. identical ethanol request produces the same analysis ID/output hash;
5. photo source metadata is echoed and changes the input hash.

They are API-level tests using `fastapi.testclient.TestClient`, but none could execute. There are no fixtures, parameterized corpus, golden JSON, snapshot fixtures, database fixtures, integration setup, coverage configuration, type checking, or browser tests in the tracked backend.

### PRD 31-case corpus comparison

| Intended PRD category | Required cases | Existing asserted coverage | Assessment |
|---|---:|---|---|
| SMILES syntax and ring closure | 6 | None | Missing. |
| Valence, sanitization, aromaticity | 6 | One impossible-valence test | Five or more cases and explicit aromaticity/generic sanitation paths missing. |
| Stereochemistry and geometry | 5 | One unassigned chiral-center test | Four or more cases; geometry/double-bond scope missing. |
| Salts, solvents, fragments | 4 | None | Missing. |
| Charge and protonation | 3 | None | Missing. |
| Tautomer and equivalent form | 3 | None | Missing. |
| Evidence and missing semantics | 4 | One assertion that configured evidence is absent | No snapshot/no-match/outside-coverage/missing-property/conflict corpus. |
| **Total** | **31** | **0 approved corpus cases; 5 general tests** | **Not implemented.** |

The five tests do not assert the PRD-required corpus record fields: raw input, expected classification, complete issue codes, deterministic locations, standardization expectations, property behavior, evidence behavior, and stable hash expectations. No expected output has chemistry-owner approval in repository evidence. Performance gates (31 cases <=10 s, preview p95 <=1.5 s) cannot be evaluated.

## 10. Security, reliability, and operational findings

| Area | Observed controls | Gaps / risk |
|---|---|---|
| Request validation | Required nonempty SMILES up to 20,000 chars; label cap; batch cap 100; nonnegative source size; lowercase SHA-256 pattern. | No request byte/body cap, source schema allow-list, source max size, content validation, or file handling. Batch minimum incorrectly permits one. |
| Chemical failure behavior | Parse/sanitize/descriptor faults are generally converted to structured results. | Standardization, depiction (silently `None`), manifest, and route-level unexpected failures lack explicit API error contract; no tests. |
| File safety | Browser has photo MIME/2 MB checks. | Backend has no upload endpoint or isolation; it cannot meet PRD parsing/file safety when ingestion is added. |
| Network/evidence | Current code has no evidence network client. | Good static offline posture, but no runtime network guard/test and no data governance implementation. |
| CORS | Development origins only, `GET`/`POST`, `Content-Type`, credentials off. | No production configuration/origin policy. |
| Secrets/privacy | `.gitignore` excludes `.env`; source metadata hash can be passed. | No secret/config loader, retention/deletion policy, access control, observability policy, or source-content protection. |
| Readiness/operations | Health exposes three version values. | No dependency/snapshot/readiness distinction, structured logs/request ID, timing, metrics, timeout/rate limit, deployment descriptor, lockfile, container/Conda/runtime pin, or backup/restore policy. |

## 11. Prioritized gap analysis / implementation plan

The PRD's suggested order is appropriate. One adjustment is explicit: **batch reliability should be resolved after the chemistry corpus and before snapshot work only if the team needs batch as the test-corpus execution surface**; otherwise frozen evidence has a stronger scientific dependency priority. The table retains the PRD order because the existing batch endpoint is small and corpus tests can run directly against the service layer initially.

| Priority | Capability | Current verified status | Evidence/files | Required change | Dependencies / blockers | Acceptance criteria | Effort |
|---|---|---|---|---|---|---|---|
| P0 | Chemistry correctness contract and 31-case corpus | NOT IMPLEMENTED | `backend/services/chemistry.py`; `backend/tests/test_analysis.py`; PRD §12 | Add chemistry-owner-approved corpus fixtures and parameterized tests for all seven categories, stable codes/locations, standardization, descriptor blocking/behavior, and deterministic hashes. Clarify unit/ambiguity contract before coding outcomes. | Supported Python/RDKit environment; chemistry-owner decisions on tolerances/rules/expected cases. | 31/31 approved cases pass three repeated hash runs; all invalid cases block descriptors; all expected nulls assert status/code/reason. | Large |
| P0 | Versioned configuration contract | PARTIALLY IMPLEMENTED | `backend/app/core/provenance.py`; `chemistry.py: PROPERTY_SPECS` | Define canonical, versioned configuration payload including standardization/descriptor definitions, units, tolerances, toolkit and snapshot details; explicitly define output hash payload. | Chemistry-owner approval; snapshot fields may initially be explicit unconfigured values. | Configuration changes to any scientific dependency change its hash; schema/golden tests document hash payload. | Medium |
| P0 | Frozen evidence snapshot and status contract | NOT IMPLEMENTED | `backend/app/services/evidence.py`; new snapshot/evidence modules required | Implement manifest-first, checksum-verified immutable local snapshot ingest/index/activation/listing and source-recorded lookup; implement coverage/no-match/missing/conflict outcomes. | Team selection of numbered ChEMBL release, PubChem CID/property scope, license/storage and checksums. | No live API calls; checksum/schema/row-count tests pass; each evidence state and provenance record is testable. | Large |
| P1 | Batch API reliability | PARTIALLY IMPLEMENTED | `models/analysis.py`; `api/routes.py`; `frontend/src/api/analysis.ts` | Change minimum to 2 when serving a PRD batch, document semantics, add per-item/whole-request failure policy, limits/timing tests, and aggregate run strategy. | Chemistry service test suite; decision on batch request/response failure behavior. | Accepts exactly 2-100; rejects 0/1/101 predictably; 31-case batch meets performance target in reference environment. | Medium |
| P1 | Persistent immutable run records/manifests | NOT IMPLEMENTED | No persistence package; frontend session files show current limitation | Add storage model/repository and create/retrieve API only after retention/storage choice; persist original request, response contract, config, snapshot dependency identity, and hashes immutably. | Decision on local/shared store, retention/privacy/deletion and migration/runtime package choice. | Created run survives browser loss; GET returns immutable stored record and manifest; no collision/overwrite ambiguity. | Large |
| P1 | Exact replay/hash verification | NOT IMPLEMENTED | No route/service/tests | Implement replay against preserved original input and exact dependency IDs; block if environment/snapshot absent; compare newly derived output hash with stored value and return diagnostics. | Persistent records, immutable snapshots, compatible runtime/version policy, defined output hash contract. | Replay never substitutes current data/config; passes equal output hash in compatible environment; blocks/reports mismatch/missing dependency correctly. | Large |
| P1 | Source registration/ingestion and report generation | NOT IMPLEMENTED / PARTIAL JSON | `SourceMetadata`; no source/report modules; `ResultsPage.tsx` client download | Add `/api/sources` only after retention/security policy; enforce type/size/storage/hash and candidate confirmation. Implement server-side JSON export and PDF only from persisted run schema. | Storage/privacy/deletion decisions; supported format/OCR/editor scope; report layout requirements. | Backend stores/verifies permitted source artifact; candidate decisions logged; JSON/PDF use one immutable run record and do not fabricate content. | Large |
| P2 | Security/performance/release hardening | PARTIALLY IMPLEMENTED | `main.py`, `models/analysis.py`, no deployment config/tests | Add request limits/timeouts/observability/error contract/readiness, production CORS/config, environment pinning, performance/accessibility/browser/release checks. | Chosen deployment model and runtime pin; security/privacy decisions. | Required NFR checks pass; readiness distinguishes no snapshot; error paths do not expose internals/secrets. | Large |

## 12. Recommended first coding task for Phase 1

**Build the chemistry-owner-approved 31-case regression corpus and parameterized service/API tests, beginning with the existing direct-SMILES contract.**

It comes first because every later capability depends on stable molecule classification, transformation identity, descriptor outputs, and hash behavior. Snapshot matching cannot be scientifically trusted until standardization and descriptor semantics have approved golden coverage, and replay hashes cannot be defined safely until the response/configuration contract is tested.

Before implementation begins, obtain these explicit inputs:

1. a supported, pinned Python/RDKit test environment (the current host is incompatible);
2. chemistry-owner approval for descriptor units/rounding/tolerances and supported ambiguity scope;
3. approved expected records for all 31 inputs, including deterministic locations only where the team agrees they are stable.

The task is complete only when the 31 corpus cases are encoded as reviewable test data, assert classifications/issue codes/standardization/property/evidence behavior, run in the supported environment, and demonstrate three identical runs per case for the current hash contract. The configuration-hash completeness task should immediately follow so future ruleset changes invalidate results deliberately.

## 13. Files inspected, created, and final confirmation

### Inspected

- Root: `.gitignore`, `README.md`, `Makefile`.
- Backend: every tracked file under `backend/`, including `pyproject.toml`, all app modules, and `tests/test_analysis.py`.
- Documentation: `docs/design-system.md` and `output/pdf/ProvenanceLab_Product_Requirements_Document_v1.0.pdf` (PRD content).
- Relevant frontend implementation needed to establish actual API, source, export, and session behavior: `frontend/src/api/analysis.ts`, `frontend/src/schemas/analysis.ts`, `frontend/src/utils/photoSource.ts`, `frontend/src/utils/runDraft.ts`, and `frontend/src/pages/ResultsPage.tsx`.
- Repository inventory, latest commit metadata, Git status, and search results for corpus/snapshot/replay/source/runtime configuration.

### Created

- `docs/backend-audit-phase-0.md` (this report only).

### Confirmation

- No application source code, schemas, dependencies, environment variables, database records, deployment settings, data, or configuration were changed.
- No tests or lint checks passed in this environment; both were blocked by absent packages, and the host Python version is outside the declared supported range.
- Important unresolved uncertainties: actual RDKit behavior/version, API startup/response serialization, all test outcomes, performance, descriptor scientific approval, ambiguity scope, evidence source/scope, persistence/retention model, replay compatibility policy, and report/file-ingestion requirements.
