# ProvenanceLab Phase 2 evidence-assistant contract

**Contract status:** working implementation contract; scientific-review approval is pending.
**Scope:** typed claim decomposition, structured assay/run/passage evidence packets, assay
comparison, deterministic verdict validation, fail-closed local-model orchestration, confidence
scoring, and research-aid output labelling.
**Not yet complete:** frozen PubChem/PMC/retraction imports, reviewed pilot scope, passage
entailment, API/UI exposure, and the locked 150-claim evaluation.

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

ChEMBL extraction accepts only a database whose internal `version` table contains `ChEMBL_36`.
The current live API is not used for this final source because it follows the latest release and may
therefore differ from release 36. The builder records release DOI `10.6019/CHEMBL.database.36`, the
official archive checksum, and the checksum of the unpacked SQLite database. Output construction is
atomic: a temporary database is sealed and verified before being renamed to the requested path.

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

The Ollama adapter always validates model output against strict Pydantic contracts and assigns
structural statement IDs (`S1`, `S2`, ...) deterministically. Its preferred mode sends JSON Schema
through Ollama's `format` parameter. The currently pinned Qwen/Ollama combination stalls on nested
array schemas, so its checked-in local configuration explicitly selects Ollama JSON mode and embeds
the same schema in the prompt. This compatibility mode remains fail-closed on validation errors and
must be recorded in run provenance; it is not to be described as schema-constrained generation.

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

## 8. Next implementation gate

Before an API endpoint is exposed, the project must add:

1. selected PubChem/PMC import adapters and a frozen retraction index that preserve raw records;
2. a reviewed pilot selection derived from (but kept separate from) the 150 evaluation claims;
3. a benchmarked passage-entailment step or an explicit decision to keep literature claims
   abstention-only;
4. confidence calibration and a retrieval-plus-LLM baseline on the locked 150-claim set;
5. integration tests against the real sealed pilot snapshot, including citation resolution; and
6. latency profiling and an operational decision about the current Qwen/Ollama combination, which
   has not met the under-ten-second warm target in local experiments.
