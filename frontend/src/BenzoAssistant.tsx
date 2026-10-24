import { useEffect, useRef, useState } from "react";
import type { CSSProperties, FormEvent, PointerEvent as ReactPointerEvent } from "react";
import { ArrowUp, ShieldCheck, X } from "lucide-react";

import { askBenzo } from "./api/benzo";
import type { BenzoChatResponse } from "./schemas/benzo";

type ConversationItem =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; response: BenzoChatResponse }
  | { id: number; role: "notice"; text: string }
  | { id: number; role: "error"; text: string };

const SUGGESTIONS = [
  "Imatinib inhibits ABL1.",
  "What is the difference between L-alanine and D-alanine?",
  "What is the molecular formula of sulfuric acid?",
  "Give me facts about aspirin",
  "How do I fix an invalid bond order?",
  "Suggest a valid aromatic ring SMILES.",
];

const VIEWPORT_MARGIN = 8;

interface AssistantPosition {
  x: number;
  y: number;
}

interface DragState {
  pointerId: number;
  offsetX: number;
  offsetY: number;
  startX: number;
  startY: number;
  lastX: number;
  lastY: number;
  moved: boolean;
}

function AnimatedBenzoMascot() {
  return <span className="benzo-character" aria-hidden="true">
    <svg viewBox="0 0 160 160" role="presentation">
      <defs>
        <linearGradient id="benzo-spectrum" x1="35" y1="32" x2="126" y2="128" gradientUnits="userSpaceOnUse">
          <stop className="benzo-character__stop benzo-character__stop--cyan" />
          <stop className="benzo-character__stop benzo-character__stop--blue" offset="0.47" />
          <stop className="benzo-character__stop benzo-character__stop--violet" offset="0.74" />
          <stop className="benzo-character__stop benzo-character__stop--magenta" offset="1" />
        </linearGradient>
      </defs>
      <g className="benzo-character__bonds" strokeWidth="5">
        <path d="M80 35V17M120 57l17-10M120 103l17 10M80 125v18M40 103l-17 10M40 57 23 47" fill="none" />
        <circle cx="80" cy="12" r="7" />
        <circle cx="143" cy="43" r="7" />
        <circle cx="143" cy="117" r="7" />
        <circle cx="80" cy="148" r="7" />
        <circle cx="17" cy="117" r="7" />
        <circle cx="17" cy="43" r="7" />
      </g>
      <path className="benzo-character__ring" d="M80 34 120 57v46l-40 23-40-23V57Z" />
      <circle className="benzo-character__inner" cx="80" cy="80" r="29" />
      <g className="benzo-character__face">
        <g className="benzo-character__eyes">
          <ellipse cx="65" cy="76" rx="4.5" ry="5.5" />
          <ellipse cx="95" cy="76" rx="4.5" ry="5.5" />
          <circle className="benzo-character__eye-shine" cx="66.5" cy="74.5" r="1.35" />
          <circle className="benzo-character__eye-shine" cx="96.5" cy="74.5" r="1.35" />
        </g>
        <g className="benzo-character__cheeks">
          <circle cx="55" cy="93" r="6" />
          <circle cx="105" cy="93" r="6" />
        </g>
        <path className="benzo-character__smile" d="M68 91q12 13 24 0" />
      </g>
    </svg>
  </span>;
}

function isGreeting(value: string): boolean {
  return /^(?:hi|hey|hello|yo|good\s+(?:morning|afternoon|evening))[!.\s]*$/i.test(value);
}

function AssistantResponse({ response }: { response: BenzoChatResponse }) {
  return <div className={`benzo-response benzo-response--${response.scope.toLowerCase()}`}>
    <div className="benzo-response__meta">
      <span className="benzo-response__badge">
        {response.scope === "ANSWERED" ? "Molecular guidance" : "Project scope only"}
      </span>
    </div>
    <p className="benzo-response__answer">{response.answer}</p>
    {response.suggestions.length ? <div className="benzo-structure-suggestions" aria-label="Structure suggestions">
      {response.suggestions.map((suggestion, index) => <article className="benzo-structure-suggestion" key={`${suggestion.title}-${index}`}>
        <strong>{suggestion.title}</strong>
        <p>{suggestion.detail}</p>
        {suggestion.smiles ? <code>{suggestion.smiles}</code> : null}
      </article>)}
    </div> : null}
  </div>;
}

export function BenzoAssistant({ currentSmiles }: { currentSmiles?: string | null }) {
  const [open, setOpen] = useState(false);
  const [claim, setClaim] = useState("");
  const [items, setItems] = useState<ConversationItem[]>([]);
  const [checking, setChecking] = useState(false);
  const [position, setPosition] = useState<AssistantPosition | null>(null);
  const [dragging, setDragging] = useState(false);
  const sequence = useRef(0);
  const shellRef = useRef<HTMLElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const positionRef = useRef<AssistantPosition | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const suppressClickRef = useRef(false);

  function clampPosition(x: number, y: number): AssistantPosition {
    const launcher = launcherRef.current;
    const width = launcher?.offsetWidth ?? 112;
    const height = launcher?.offsetHeight ?? 154;
    return {
      x: Math.max(VIEWPORT_MARGIN, Math.min(x, window.innerWidth - width - VIEWPORT_MARGIN)),
      y: Math.max(VIEWPORT_MARGIN, Math.min(y, window.innerHeight - height - VIEWPORT_MARGIN)),
    };
  }

  useEffect(() => {
    const keepInViewport = () => {
      const current = positionRef.current;
      if (!current) return;
      const next = clampPosition(current.x, current.y);
      positionRef.current = next;
      setPosition(next);
    };
    window.addEventListener("resize", keepInViewport);
    return () => window.removeEventListener("resize", keepInViewport);
  }, []);

  function beginDrag(event: ReactPointerEvent<HTMLButtonElement>) {
    if (open || event.button !== 0) return;
    const shell = shellRef.current;
    if (!shell) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const start = { x: bounds.left, y: bounds.top };
    positionRef.current = start;
    shell.style.left = `${start.x}px`;
    shell.style.top = `${start.y}px`;
    shell.style.right = "auto";
    shell.style.bottom = "auto";
    dragRef.current = {
      pointerId: event.pointerId,
      offsetX: event.clientX - bounds.left,
      offsetY: event.clientY - bounds.top,
      startX: event.clientX,
      startY: event.clientY,
      lastX: start.x,
      lastY: start.y,
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
  }

  function continueDrag(event: ReactPointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current;
    const shell = shellRef.current;
    if (!drag || !shell || drag.pointerId !== event.pointerId) return;
    if (Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > 4) {
      drag.moved = true;
    }
    const next = clampPosition(event.clientX - drag.offsetX, event.clientY - drag.offsetY);
    drag.lastX = next.x;
    drag.lastY = next.y;
    positionRef.current = next;
    shell.style.left = `${next.x}px`;
    shell.style.top = `${next.y}px`;
    setPosition(next);
  }

  function endDrag(event: ReactPointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    suppressClickRef.current = drag.moved;
    dragRef.current = null;
    setDragging(false);
    setPosition({ x: drag.lastX, y: drag.lastY });
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    window.setTimeout(() => {
      suppressClickRef.current = false;
    }, 0);
  }

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
          text: "Hey! Ask me about ProvenanceLab, a molecule, its bonds, or a SMILES structure.",
        },
      ]);
      setClaim("");
      return;
    }
    setItems((current) => [...current, userItem]);
    setClaim("");
    setChecking(true);
    try {
      const response = await askBenzo(submitted, currentSmiles);
      setItems((current) => [
        ...current,
        { id: ++sequence.current, role: "assistant", response },
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Benzo could not answer that question.";
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

  const positionStyle: CSSProperties | undefined = position
    ? { left: position.x, top: position.y, right: "auto", bottom: "auto" }
    : undefined;

  return <aside
    ref={shellRef}
    className={`benzo-shell${open ? " benzo-shell--open" : ""}${dragging ? " benzo-shell--dragging" : ""}`}
    style={positionStyle}
  >
    {open ? <section
      id="benzo-assistant-panel"
      className="benzo-panel"
      role="dialog"
      aria-label="Benzo molecular assistant"
    >
      <header className="benzo-header">
        <AnimatedBenzoMascot />
        <div><strong>Ask Benzo</strong></div>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close Benzo assistant">
          <X size={18} />
        </button>
      </header>

      <div className="benzo-feed" aria-live="polite">
        {!items.length ? <div className="benzo-suggestions">
          <span>Try a molecular question</span>
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
            ? <div key={item.id} className="benzo-message benzo-message--error"><strong>Couldn’t answer that</strong><span>{item.text}</span></div>
            : <AssistantResponse key={item.id} response={item.response} />)}
        {checking ? <div className="benzo-thinking" role="status"><AnimatedBenzoMascot /><span>Benzo is checking the molecule and project context…</span></div> : null}
      </div>

      <form className="benzo-composer" onSubmit={(event) => void submitClaim(event)}>
        <label htmlFor="benzo-claim">Molecular question</label>
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
            placeholder="Ask about bonds, SMILES, or this project…"
            rows={2}
            maxLength={4_000}
          />
          <button type="submit" disabled={!claim.trim() || checking} aria-label="Ask Benzo">
            <ArrowUp size={18} />
          </button>
        </div>
      </form>
      <footer className="benzo-disclaimer"><ShieldCheck size={14} /> Project-scoped guidance. Validate suggested structures before use.</footer>
    </section> : null}

    <button
      ref={launcherRef}
      type="button"
      className="benzo-launcher"
      onPointerDown={beginDrag}
      onPointerMove={continueDrag}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onLostPointerCapture={endDrag}
      onClick={() => {
        if (suppressClickRef.current) return;
        setOpen((current) => !current);
      }}
      aria-expanded={open}
      aria-controls="benzo-assistant-panel"
      aria-label={open ? "Close Benzo molecular assistant" : "Open Benzo molecular assistant"}
      title={open ? "Close Benzo" : "Drag Benzo or click to ask"}
    >
      <span className="benzo-launcher__label">Hi! How can I help? ✨</span>
      <AnimatedBenzoMascot />
    </button>
  </aside>;
}
