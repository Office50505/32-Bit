import type { MoleculeCandidate } from "./domain";

interface Props { molecule: MoleculeCandidate; compact?: boolean; zoom?: number; onIssueClick?: () => void }

export function Molecule2D({ molecule, compact = false, zoom = 1, onIssueClick }: Props) {
  const common = { fill: "none", stroke: "#263849", strokeWidth: 3, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg className={`molecule-2d ${compact ? "molecule-2d--compact" : ""}`} viewBox="0 0 560 360" role="img" aria-label={`${molecule.label} illustrative 2D structure`}>
      <g transform={`translate(280 180) scale(${zoom}) translate(-280 -180)`}>
        {molecule.id === "aspirin" ? <>
          <g {...common}>
            <path d="M216 103 L284 143 L284 223 L216 263 L148 223 L148 143 Z" />
            <path d="M215 115 L271 148 M270 218 L216 250 M159 217 L159 149" strokeWidth="2" />
            <path d="M216 103 L216 62 M216 62 L257 39 M216 62 L173 39 M284 223 L326 247 M353 247 L398 223 M398 223 L443 246 M398 223 L398 180" />
            <path d="M404 221 L404 181" strokeWidth="2" />
          </g>
          <g className="molecule-label"><text x="258" y="42">OH</text><text x="129" y="43">O</text><text x="323" y="255">O</text><text x="384" y="173">O</text><text x="444" y="258">CH₃</text></g>
        </> : molecule.id === "compound-7b" ? <>
          <g {...common}><path d="M105 215 L185 165 L264 212 L345 164 L425 211 M264 212 L264 121" /></g>
          <g className="molecule-label"><text x="244" y="111">OH</text><text x="86" y="243">CH₃</text><text x="408" y="239">CH₃</text></g>
          <circle cx="264" cy="212" r="21" fill="none" stroke="#d97706" strokeWidth="2" strokeDasharray="5 5" />
          {!compact && <text x="290" y="247" className="molecule-hint">configuration unassigned</text>}
        </> : <>
          <g {...common}><path d="M42 210 L92 175 L142 210 L192 175 L242 210 L292 175 L342 210 M342 210 L396 168 M342 210 L396 252" /></g>
          <text x="326" y="219" className="molecule-label molecule-label--oxygen">O</text>
          <circle cx="342" cy="210" r="31" className="molecule-error-halo" onClick={onIssueClick}>
            <title>Oxygen atom 7: impossible valence</title>
          </circle>
          {!compact && <text x="376" y="209" className="molecule-error-label">Atom 7</text>}
        </>}
      </g>
    </svg>
  );
}
