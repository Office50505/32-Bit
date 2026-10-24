import { type FormEvent, useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowLeft, Check, FileText, Pencil, Search } from "lucide-react";

import { ComputedMolecule3D } from "./ComputedMolecule3D";
import type { ExtractedSourceCandidate } from "./domain";
import { LiveMoleculeSvg } from "./LiveMoleculeSvg";
import type { AnalyzeResponse } from "./schemas/analysis";
import { MoleculeStatusBadge } from "./StatusBadge";

type CandidateFilter = "all" | "ready" | "review" | "invalid";

interface Props {
  filename: string;
  sourceUrl: string | null;
  candidates: ExtractedSourceCandidate[];
  previews: AnalyzeResponse[];
  selectedIndices: Set<number>;
  confirming: boolean;
  onToggle: (index: number) => void;
  onCorrect: (index: number, structure: string) => Promise<void>;
  onSelectReady: () => void;
  onConfirm: () => void;
  onBack: () => void;
}

export function MoleculeCollectionReview({
  filename,
  sourceUrl,
  candidates,
  previews,
  selectedIndices,
  confirming,
  onToggle,
  onCorrect,
  onSelectReady,
  onConfirm,
  onBack,
}: Props) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [filter, setFilter] = useState<CandidateFilter>("all");
  const [search, setSearch] = useState("");
  const [correctedSmiles, setCorrectedSmiles] = useState("");
  const [correcting, setCorrecting] = useState(false);
  const [correctionError, setCorrectionError] = useState("");
  const activePreview = previews[activeIndex];
  const activeCandidate = candidates[activeIndex];
  const readyCount = previews.filter((item) => item.status === "valid").length;
  const reviewCount = previews.filter((item) => item.status === "ambiguous").length;
  const invalidCount = previews.filter((item) => item.status === "invalid").length;
  const totalMentions = candidates.reduce((total, item) => total + item.mentions.length, 0);
  const visible = useMemo(() => previews.flatMap((preview, index) => {
    const matchesFilter = filter === "all"
      || (filter === "ready" && preview.status === "valid")
      || (filter === "review" && preview.status === "ambiguous")
      || (filter === "invalid" && preview.status === "invalid");
    const candidate = candidates[index];
    const matchesSearch = `${candidate?.label ?? ""} ${preview.raw_input}`
      .toLowerCase()
      .includes(search.toLowerCase());
    return matchesFilter && matchesSearch ? [{ preview, candidate, index }] : [];
  }), [candidates, filter, previews, search]);

  useEffect(() => {
    if (!activeCandidate) return;
    setCorrectedSmiles(activeCandidate.smiles);
    setCorrectionError("");
  }, [activeCandidate]);

  useEffect(() => {
    if (activeIndex >= candidates.length) setActiveIndex(Math.max(0, candidates.length - 1));
  }, [activeIndex, candidates.length]);

  if (!activeCandidate || !activePreview) return null;
  const activeMention = activeCandidate.mentions[0];
  const sourceHref = sourceUrl && activeMention?.page
    ? `${sourceUrl}#page=${activeMention.page}`
    : sourceUrl;

  async function submitCorrection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCorrecting(true);
    setCorrectionError("");
    try {
      await onCorrect(activeIndex, correctedSmiles);
    } catch (error) {
      setCorrectionError(error instanceof Error ? error.message : "The correction could not be checked.");
    } finally {
      setCorrecting(false);
    }
  }

  return <section className="collection-review" aria-labelledby="collection-review-title">
    <header className="collection-review__header">
      <div>
        <span className="section-kicker">02 / CONFIRM COLLECTION</span>
        <h2 id="collection-review-title">{candidates.length} unique molecules found</h2>
        <p>{totalMentions} source mentions in {filename}. Review the collection before creating the run.</p>
      </div>
      <div className="collection-review__summary" aria-label="Extraction summary">
        <span><strong>{readyCount}</strong> ready</span>
        <span><strong>{reviewCount}</strong> review</span>
        <span><strong>{invalidCount}</strong> invalid</span>
      </div>
    </header>

    <div className="collection-review__workspace">
      <aside className="collection-roster" aria-label="Extracted molecules">
        <label className="collection-search"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search molecules" /></label>
        <div className="collection-filters" role="group" aria-label="Filter candidates">
          {(["all", "ready", "review", "invalid"] as CandidateFilter[]).map((item) => <button key={item} className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item}</button>)}
        </div>
        <div className="collection-roster__rows">
          {visible.map(({ preview, candidate, index }) => <article key={candidate.id} className={`collection-row${activeIndex === index ? " collection-row--active" : ""}`}>
            <label className="collection-row__check" title={preview.status === "invalid" ? "Invalid candidates cannot be confirmed" : "Include in run"}>
              <input type="checkbox" checked={selectedIndices.has(index)} disabled={preview.status === "invalid"} onChange={() => onToggle(index)} />
              <span />
            </label>
            <button type="button" onClick={() => setActiveIndex(index)}>
              <span className="collection-row__thumbnail">{preview.status === "invalid" ? <AlertCircle size={20} /> : <LiveMoleculeSvg svg={preview.depiction_svg} />}</span>
              <span className="collection-row__copy"><strong>{candidate.label}</strong><code>{candidate.smiles}</code><small>{candidate.mentions.length} mention{candidate.mentions.length === 1 ? "" : "s"} · {candidate.mentions[0]?.locator}</small></span>
              <MoleculeStatusBadge status={preview.status} compact />
            </button>
          </article>)}
          {!visible.length ? <p className="collection-roster__empty">No molecules match this filter.</p> : null}
        </div>
      </aside>

      <section className="collection-model" aria-label="Selected molecule 3D model">
        <div className="collection-panel-heading"><div><span>Selected molecule</span><strong>{activeCandidate.label}</strong></div><MoleculeStatusBadge status={activePreview.status} /></div>
        <div className="collection-model__canvas">
          <ComputedMolecule3D
            structure={activePreview.standardized_smiles}
            label={activeCandidate.label}
            status={activePreview.status}
            autorotate
            resetSignal={0}
            zoom={1}
          />
        </div>
        <div className="collection-model__identity"><span>Submitted SMILES</span><code>{activeCandidate.smiles}</code></div>
      </section>

      <aside className="collection-source" aria-label="Source provenance">
        <div className="collection-panel-heading"><div><span>Source evidence</span><strong>{filename}</strong></div><FileText size={18} /></div>
        <div className="collection-source__body">
          <dl>
            <div><dt>Location</dt><dd>{activeMention?.locator ?? "Source location unavailable"}</dd></div>
            <div><dt>Confidence</dt><dd>{activeCandidate.confidence.replace("-", " ")}</dd></div>
            <div><dt>Occurrences</dt><dd>{activeCandidate.mentions.length}</dd></div>
          </dl>
          {activeMention?.excerpt ? <blockquote>{activeMention.excerpt}</blockquote> : null}
          {activeCandidate.mentions.length > 1 ? <div className="collection-source__mentions"><strong>All mentions</strong>{activeCandidate.mentions.map((mention, index) => <span key={`${mention.locator}-${index}`}>{mention.locator}</span>)}</div> : null}
          <form className="collection-correction" onSubmit={(event) => void submitCorrection(event)}>
            <label htmlFor="collection-correction-smiles">Correct extracted SMILES</label>
            <input id="collection-correction-smiles" value={correctedSmiles} onChange={(event) => setCorrectedSmiles(event.target.value)} spellCheck={false} />
            <button className="button button--outline" type="submit" disabled={correcting || correctedSmiles.trim() === activeCandidate.smiles}><Pencil size={14} />{correcting ? "Checking…" : "Re-check candidate"}</button>
            {correctionError ? <small role="alert">{correctionError}</small> : null}
          </form>
          {sourceHref ? <a href={sourceHref} target="_blank" rel="noreferrer">Open original source</a> : null}
          {activePreview.status === "invalid" ? <p className="collection-source__warning"><AlertCircle size={16} />{activePreview.issues[0]?.explanation ?? "The extracted structure is invalid."}</p> : null}
        </div>
      </aside>
    </div>

    <footer className="collection-actions">
      <button className="button button--quiet" type="button" onClick={onBack}><ArrowLeft size={16} /> Back to source</button>
      <div>
        <button className="button button--outline" type="button" onClick={onSelectReady}>Select all ready</button>
        <button className="button button--primary" type="button" disabled={!selectedIndices.size || confirming} onClick={onConfirm}><Check size={17} />{confirming ? "Creating run…" : `Confirm ${selectedIndices.size} selected`}</button>
      </div>
    </footer>
  </section>;
}
