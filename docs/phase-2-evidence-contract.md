# ProvenanceLab Phase 2 evidence-assistant contract

**Contract status:** initial implementation contract; scientific-review approval is pending.  
**Scope:** typed claim decomposition, evidence packets, deterministic verdict validation, and
research-aid output labelling.  
**Non-goal in this increment:** live ChEMBL/PubChem ingestion, dense passage retrieval, Ollama
calls, confidence calibration, and the 150-claim evaluation.

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

## 4. Initial disagreement policy

The initial validator refuses `SUPPORTED` when the cited direct evidence includes a direct
contradiction. The later assay-comparability engine may distinguish compatible from incompatible
assays, but it must do so using typed dimensions such as molecule parent, target, organism,
endpoint, assay type, units, relation operator, and experimental context. Until then, direct
disagreement forces abstention rather than an LLM-selected winner.

## 5. Confidence contract

Confidence is `HIGH`, `MEDIUM`, or `LOW` and must be produced by a versioned deterministic
calibration method. The model does not emit a percentage. Benchmark accuracy and case count are
reported together only after they are measured on the frozen evaluation set.

Planned factors are entity-match certainty, evidence directness, assay-target confidence, source
independence, comparable-assay agreement, measurement flags, citation validity, retraction status,
and retrieval margin.

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

## 8. Next implementation gate

Before an API endpoint is exposed, the project must add:

1. selected PubChem/PMC import adapters that preserve raw records;
2. higher-level molecule and target resolution with explicit ambiguity stops;
3. claim-routing orchestration around the pinned Ollama structured-output adapter;
4. a deterministic confidence implementation backed by benchmark calibration; and
5. integration tests proving that retrieved citations resolve to the sealed pilot snapshot.
