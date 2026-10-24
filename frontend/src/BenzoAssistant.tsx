import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { ArrowUp, ChevronDown, FlaskConical, ShieldCheck, X } from "lucide-react";

import { checkEvidenceClaim } from "./api/evidence";
import type {
  ClaimCheckResponse,
  EvidenceCitation,
  EvidenceStatementVerdict,
  EvidenceVerdict,
} from "./schemas/evidence";

type ConversationItem =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; response: ClaimCheckResponse }
  | { id: number; role: "notice"; text: string }
  | { id: number; role: "error"; text: string };

const VERDICT_LABELS: Record<EvidenceVerdict, string> = {
  SUPPORTED: "Supported",
  CONTRADICTED: "Contradicted",
  INSUFFICIENT_EVIDENCE: "Insufficient evidence",
  OUT_OF_SCOPE: "Out of scope",
};

const SUGGESTIONS = [
  "Imatinib inhibits ABL1.",
  "What is the difference between L-alanine and D-alanine?",
];

function isGreeting(value: string): boolean {
  return /^(?:hi|hey|hello|yo|good\s+(?:morning|afternoon|evening))[!.\s]*$/i.test(value);
}

function citationMeasurement(citation: EvidenceCitation): string | null {
  if (citation.value === null || citation.value === undefined) return null;
  return `${citation.relation ?? ""}${citation.value}${citation.unit ? ` ${citation.unit}` : ""}`;
}

function Citation({ citation, index }: { citation: EvidenceCitation; index: number }) {
  const measurement = citationMeasurement(citation);
  const assayDescription = citation.assay_conditions.description;
  const recordKind = citation.assay_conditions.record_kind;
  const compoundTitle = citation.assay_conditions.title;
  const molecularFormula = citation.assay_conditions.molecular_formula;
  const molecularWeight = citation.assay_conditions.molecular_weight;
  const isomericSmiles = citation.assay_conditions.isomeric_smiles;
  const sourceUrl = citation.assay_conditions.source_url;
  const sourceLabel = recordKind === "PUBCHEM_COMPOUND"
    ? "PubChem compound"
    : citation.source_type.replaceAll("_", " ");
  return <details className="benzo-citation">
    <summary>
      <span>[{index + 1}] {sourceLabel}</span>
      <ChevronDown size={14} />
    </summary>
    <dl>
      <div><dt>Record</dt><dd>{citation.source_record_id}</dd></div>
      {measurement ? <div><dt>Measurement</dt><dd>{measurement}</dd></div> : null}
      {citation.paper_id ? <div><dt>Paper</dt><dd>{citation.paper_id}</dd></div> : null}
      {typeof assayDescription === "string" && assayDescription
        ? <div><dt>Assay</dt><dd>{assayDescription}</dd></div>
        : null}
      {recordKind === "PUBCHEM_COMPOUND" && typeof compoundTitle === "string"
        ? <div><dt>Compound</dt><dd>{compoundTitle}</dd></div>
        : null}
      {typeof molecularFormula === "string"
        ? <div><dt>Formula</dt><dd>{molecularFormula}</dd></div>
        : null}
      {typeof molecularWeight === "string"
        ? <div><dt>Weight</dt><dd>{molecularWeight} g/mol</dd></div>
        : null}
      {typeof isomericSmiles === "string"
        ? <div><dt>Isomeric SMILES</dt><dd>{isomericSmiles}</dd></div>
        : null}
      {citation.passage_locator ? <div><dt>Passage</dt><dd>{citation.passage_locator}</dd></div> : null}
      <div><dt>Retraction check</dt><dd>{recordKind === "PUBCHEM_COMPOUND" ? "Not applicable" : citation.retraction_status}</dd></div>
      <div><dt>Snapshot</dt><dd>{citation.snapshot_id}</dd></div>
      {typeof sourceUrl === "string" && sourceUrl.startsWith("https://")
        ? <div><dt>Source</dt><dd><a href={sourceUrl} target="_blank" rel="noreferrer">PubChem record</a></dd></div>
        : null}
    </dl>
  </details>;
}

function VerdictCard({ result }: { result: EvidenceStatementVerdict }) {
  return <article className="benzo-verdict">
    <div className="benzo-verdict__meta">
      <span className={`benzo-verdict__badge benzo-verdict__badge--${result.verdict.toLowerCase()}`}>
        {VERDICT_LABELS[result.verdict]}
      </span>
      <span>{result.confidence.level.toLowerCase()} confidence</span>
    </div>
    <h4>{result.statement.text}</h4>
    <p>{result.reason}</p>
    {result.conflict_summary ? <p className="benzo-verdict__conflict">{result.conflict_summary}</p> : null}
    {result.citations.length ? <div className="benzo-citations" aria-label="Evidence citations">
      {result.citations.map((citation, index) => (
        <Citation key={citation.evidence_id} citation={citation} index={index} />
      ))}
    </div> : <p className="benzo-verdict__empty">No eligible citation was available for this verdict.</p>}
  </article>;
}

function AssistantResponse({ response }: { response: ClaimCheckResponse }) {
  return <div className="benzo-response">
    {response.verdicts.map((result) => (
      <VerdictCard key={result.statement.statement_id} result={result} />
    ))}
    <p className="benzo-response__source">
      {response.manifest.evidence_snapshot_id} · {response.manifest.model_name}
    </p>
  </div>;
}

export function BenzoAssistant() {
  const [open, setOpen] = useState(false);
  const [claim, setClaim] = useState("");
  const [items, setItems] = useState<ConversationItem[]>([]);
  const [checking, setChecking] = useState(false);
  const sequence = useRef(0);

  async function submitClaim(event?: FormEvent) {
    event?.preventDefault();
    const submitted = claim.trim();
    if (!submitted || checking) return;
    const userItem: ConversationItem = {
      id: ++sequence.current,
      role: "user",
      text: submitted,
    };
    if (isGreeting(submitted)) {
      setItems((current) => [
        ...current,
        userItem,
        {
          id: ++sequence.current,
          role: "notice",
          text: "Hey! Give me a molecule question or a scientific claim, and I’ll show the frozen records behind my answer.",
        },
      ]);
      setClaim("");
      return;
    }
    setItems((current) => [...current, userItem]);
    setClaim("");
    setChecking(true);
    try {
      const response = await checkEvidenceClaim(submitted);
      setItems((current) => [
        ...current,
        { id: ++sequence.current, role: "assistant", response },
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Benzo could not check this claim.";
      setItems((current) => [
        ...current,
        { id: ++sequence.current, role: "error", text: message },
      ]);
    } finally {
      setChecking(false);
    }
  }

  function useSuggestion(suggestion: string) {
    setClaim(suggestion);
  }

  return <aside className={`benzo-shell ${open ? "benzo-shell--open" : ""}`}>
    {open ? <section
      id="benzo-assistant-panel"
      className="benzo-panel"
      role="dialog"
      aria-label="Benzo evidence assistant"
    >
      <header className="benzo-header">
        <img src="/benzo-happy.png" alt="" />
        <div><strong>Ask Benzo</strong><span><i /> Frozen evidence assistant</span></div>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close Benzo assistant">
          <X size={18} />
        </button>
      </header>

      <div className="benzo-feed" aria-live="polite">
        <div className="benzo-intro">
          <span className="benzo-intro__icon"><FlaskConical size={17} /></span>
          <div><strong>I check claims, not predict outcomes.</strong><p>The assay pilot covers imatinib and ABL1. For molecule identity and structure questions, I can freeze cited PubChem records on demand.</p></div>
        </div>
        {!items.length ? <div className="benzo-suggestions">
          <span>Try a claim</span>
          {SUGGESTIONS.map((suggestion) => (
            <button type="button" key={suggestion} onClick={() => useSuggestion(suggestion)}>
              {suggestion}
            </button>
          ))}
        </div> : null}
        {items.map((item) => item.role === "user"
          ? <p key={item.id} className="benzo-message benzo-message--user">{item.text}</p>
          : item.role === "notice"
            ? <div key={item.id} className="benzo-message benzo-message--notice">{item.text}</div>
          : item.role === "error"
            ? <div key={item.id} className="benzo-message benzo-message--error"><strong>Couldn’t check that claim</strong><span>{item.text}</span></div>
            : <AssistantResponse key={item.id} response={item.response} />)}
        {checking ? <div className="benzo-thinking" role="status"><img src="/benzo-happy.png" alt="" /><span>Benzo is checking the frozen records…</span></div> : null}
      </div>

      <form className="benzo-composer" onSubmit={(event) => void submitClaim(event)}>
        <label htmlFor="benzo-claim">Scientific claim</label>
        <div>
          <textarea
            id="benzo-claim"
            value={claim}
            onChange={(event) => setClaim(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submitClaim();
              }
            }}
            placeholder="Ask about a molecule or paste a claim…"
            rows={2}
            maxLength={20_000}
          />
          <button type="submit" disabled={!claim.trim() || checking} aria-label="Check claim">
            <ArrowUp size={18} />
          </button>
        </div>
      </form>
      <footer className="benzo-disclaimer"><ShieldCheck size={14} /> Research aid only—not a prediction of efficacy or safety.</footer>
    </section> : null}

    <button
      type="button"
      className="benzo-launcher"
      onClick={() => setOpen((current) => !current)}
      aria-expanded={open}
      aria-controls="benzo-assistant-panel"
      aria-label={open ? "Close Benzo evidence assistant" : "Open Benzo evidence assistant"}
    >
      <span className="benzo-launcher__label">Ask Benzo</span>
      <img src="/benzo-happy.png" alt="Benzo, the ProvenanceLab evidence assistant" />
    </button>
  </aside>;
}
