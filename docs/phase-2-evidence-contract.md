# ProvenanceLab Phase 2 evidence-assistant contract

**Contract status:** working implementation contract; scientific-review approval is pending.
**Scope:** typed claim decomposition, structured assay/run/passage evidence packets, assay
comparison, deterministic verdict validation, fail-closed local-model orchestration, confidence
scoring, and research-aid output labelling.
**Not yet complete:** acquisition of the reviewed frozen source files, the final combined pilot
bundle, reviewed pilot scope, passage entailment, API/UI exposure, and the locked 150-claim
evaluation.

## 1. Authority boundary

The language model may decompose claims and propose a verdict. It is never the authority for
citations, retraction exclusions, experimental-versus-computed evidence, entity resolution, or
whether a decisive verdict is permitted. Those checks are deterministic.

Every visible report must include exactly:

> Research aid only. This report summarizes available evidence and is not a prediction of
> clinical efficacy or safety.

## 2. Verdict contract

| Verdict | Deterministic minimum |
|---|---|
| `SUPPORTED` | Resolved entities, at least one supplied direct supporting citation, no deciding retracted citation, and experimental support for biological-activity claims. |
| `CONTRADICTED` | Resolved entities and at least one supplied direct contradicting citation. Absence of support is not contradiction. Biological-activity contradiction requires experimental evidence. |
| `INSUFFICIENT_EVIDENCE` | A stable reason code explaining the abstention, such as ambiguity, indirect evidence, computed-only evidence, retracted-only evidence, disagreement, or snapshot coverage. |
| `OUT_OF_SCOPE` | A scope-policy reason code and no fabricated scientific citation. Clinical predictions, safety predictions, personalized advice, and unsupported future efficacy are out of scope. |

For `SUPPORTED` and `CONTRADICTED`, citation IDs must exist in the exact evidence packet supplied
to the model. A run record may support computed-property claims, but it cannot independently
support or contradict biological activity.

For `INSUFFICIENT_EVIDENCE`, citations may identify inspected or excluded records, but the reason
code is authoritative. A no-evidence result must not fabricate a citation. For `OUT_OF_SCOPE`, the
scope policy is the decision basis; a scientific citation is neither required nor permitted merely
to satisfy a UI field.

## 3. Retraction policy

- `RETRACTED`: may be shown only as excluded context; cannot decide `SUPPORTED` or `CONTRADICTED`.
- `EXPRESSION_OF_CONCERN`: may be considered but must emit a prominent warning and reduce the
  later deterministic confidence calculation.
- `CORRECTED`: requires downstream inspection of whether the correction affects the cited result.
- `REINSTATED`: is not treated as retracted after the frozen record verifies reinstatement.
- `UNKNOWN`: emits a warning and limits confidence.

## 4. Assay disagreement policy

The assay-comparability engine normalizes supported molar units, preserves censor operators, and
compares molecule parent, target, organism, endpoint, assay type, and typed experimental context.
Opposite stances under matching typed context create a decision conflict and force abstention.
Opposite stances under different context are reported as contextual disagreement but are not
silently treated as a direct contradiction. Ten-fold numeric divergence is surfaced even when it
does not change the qualitative statement verdict. The model cannot select a winner when the
deterministic layer identifies a comparable direct conflict.

## 5. Confidence contract

Confidence is `HIGH`, `MEDIUM`, or `LOW` and must be produced by a versioned deterministic
calibration method. The model does not emit a percentage. Benchmark accuracy and case count are
reported together only after they are measured on the frozen evaluation set.

Version 1 factors are entity-match certainty, evidence directness, assay-target confidence, source
independence, comparable-assay agreement, measurement flags, citation validity, retraction status,
and direct-evidence coverage. A score of at least 0.86 reaches `HIGH` only when at least two usable
direct records from independent papers or assays are present and retraction status is sufficiently
known. A single source is capped at `MEDIUM`; rejected model output is capped at `LOW`. These are
engineering thresholds, not calibrated probabilities, until the frozen evaluation set supplies
per-band accuracy and case count.

## 6. Reproducibility fields

The final manifest records the pinned model name and digest, frozen evidence snapshot ID, input
hash, configuration hash, and output hash. Evidence items carry a stable evidence ID, source record
ID, snapshot ID, raw-record hash, source type, experimental/computed basis, directness, stance, and
retraction status.

## 7. SQLite snapshot boundary

The initial evidence store is a versioned SQLite database with normalized molecule, target, assay,
activity, paper, passage, retraction, run-record, and evidence-item tables. SQLite FTS5 supplies the
lexical passage index. Snapshot construction is writable; claim checking opens the completed file
in read-only, immutable mode.

The full-release ChEMBL extractor accepts only a database whose internal `version` table contains
`ChEMBL_36`. It records release DOI `10.6019/CHEMBL.database.36`, the official archive checksum,
and the checksum of the unpacked SQLite database. Output construction is atomic: a temporary
database is sealed and verified before being renamed to the requested path.

For storage-constrained development, the official ChEMBL Data Web Services are also supported as
a snapshot-construction source. This is not a live-data runtime mode. The acquisition command pins
an expected numbered release, saves the exact JSON response bytes, records each request URL and
response SHA-256, verifies pagination, and refuses release drift. The importer verifies all hashes,
screens source documents against the frozen Retraction Watch index, normalizes the selected rows,
and seals a local SQLite file. Claim checking then uses that SQLite file in immutable read-only
mode and makes no ChEMBL web requests.

The API reported `ChEMBL_37` with release date `2026-05-01` when checked on `2026-10-24`. The
checked-in API example therefore explicitly pins `ChEMBL_37`; it must not be labelled as ChEMBL 36.
If evaluation rules require release 36 specifically, the API cannot substitute for the archived
release-36 database. A release-36 extract must instead be prepared once on a machine with enough
storage and transferred as the much smaller scoped SQLite snapshot.

Example builder invocation after the official archive has been downloaded, checksum-verified, and
unpacked:

```bash
PYTHONPATH=backend python -m app.evidence.build_chembl36_snapshot \
  --source-db /absolute/path/to/chembl_36.db \
  --selection backend/config/evidence/pilot-selection.example.json \
  --output /absolute/path/to/evidence.sqlite \
  --snapshot-id chembl36-pilot-v1 \
  --created-at 2026-10-24T00:00:00Z
```

The example selection is intentionally a one-molecule smoke test, not the final benchmark scope.
The reviewed pilot manifest must expand it only after the claim set defines the required molecules,
targets, organisms, and endpoints.

Storage-constrained ChEMBL 37 API build:

```bash
PYTHONPATH=backend python -m app.evidence.build_chembl_api_snapshot \
  --selection backend/config/evidence/pilot-selection-api.example.json \
  --raw-dir data/raw/chembl-api/chembl37-pilot-v1 \
  --output data/processed/chembl-api-37-pilot-v1.sqlite \
  --snapshot-id chembl-api-37-pilot-v1 \
  --created-at 2026-10-24T00:00:00Z \
  --retraction-watch-csv data/raw/retractions/retraction_watch-2026-10-24.csv
```

If `--raw-dir` already contains a verified acquisition, the command reuses it without fetching.
Add `--offline` to require that behavior and fail if the raw snapshot is absent. A real
imatinib/ABL1 smoke build produced 131 activity records, 131 assay records, and 43 source-document
records from 588 KiB of frozen JSON, then sealed a 512 KiB SQLite snapshot. These counts demonstrate
the pipeline only; they are not the reviewed pilot or evaluation corpus.

Question-scoped molecule identity, formula, molecular-weight, and two-compound comparison requests
can acquire PubChem PUG REST property records on demand. The first request saves the exact response
bytes and an atomic manifest under `data/runtime/pubchem-compound-snapshots/`, including the request
URL, retrieval time, CID, and response SHA-256. Later requests verify and reuse that immutable local
record instead of calling PubChem again. These structured records may support identity and structure
answers, but they must never support a biological-activity claim.

The Ollama adapter always validates model output against strict Pydantic contracts and assigns
structural statement IDs (`S1`, `S2`, ...) deterministically. It sends compact JSON Schema through
Ollama's `format` parameter. The model-facing evidence and verdict contracts are deliberately
bounded for reliable local inference; deterministic validation still evaluates the complete
retrieved packet and fails closed on an invalid model response.

Each snapshot records the source version and source hash. Sealing computes a deterministic digest
over canonical snapshot metadata and every normalized source row. FTS rows are derived search data
and are therefore excluded from that content digest. A sealed snapshot rejects further builder
writes, and runtime startup can verify its digest before serving claims.

The orchestration layer verifies every snapshot hash and the pinned Ollama model identity before
accepting work. Deterministic routing can override a bad model claim-type label. Comparable assay
conflicts and no-direct-evidence cases bypass model verdict selection. If the model invents a
citation or proposes a forbidden verdict, the output becomes `INSUFFICIENT_EVIDENCE` with
`MODEL_OUTPUT_REJECTED` and low confidence. The response manifest hashes the request,
configuration, frozen snapshot identities, and verdict payload.

Paper retrieval is deliberately conservative in the current increment. FTS5 returns an exact
paper ID, section/paragraph/character locator, passage text, passage hash, and retraction status,
but the passage is labelled `CONTEXT_ONLY` and neutral until a passage-entailment method has been
evaluated. This prevents lexical retrieval alone from turning prose into a supported mechanism.

Frozen importers are implemented for selected PubChem concise BioAssay JSON, Europe PMC open-access
JATS XML, and the Crossref Retraction Watch CSV. PubChem rows are whitelisted by reviewed AID/CID
selection, retain AID/SID/CID identity and raw-row hashes, and normalize reported micromolar values
to nanomolar values without discarding the original. JATS passages retain PMCID, paper identifiers,
section, paragraph, character offsets, text hashes, article license, and full-XML hash. The
Retraction Watch index normalizes DOI/PMID identifiers, records each notice, and handles a later
dated reinstatement without erasing the earlier retraction record. All source snapshots are sealed
before runtime use.

## 8. Next implementation gate

Before an API endpoint is exposed, the project must add:

1. approve the final release-pinned selection, acquire and checksum its official API responses (or
   use the numbered full-release database), then build and integration-test the combined sealed
   pilot database;
2. define a reviewed pilot selection independently of the locked 150 evaluation claims;
3. supply and freeze the 150-claim gold set with reviewer labels and evidence references;
4. add a benchmarked passage-entailment step or explicitly keep literature claims
   abstention-only;
5. calibrate confidence and run the retrieval-plus-LLM baseline on that locked set;
6. expose the reviewed service through the API and build the evidence-assistant UI; and
7. profile latency and make an operational decision about the current Qwen/Ollama combination, which
   has not met the under-ten-second warm target in local experiments.
