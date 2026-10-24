import type { RefObject } from "react";
import { Check, Pencil, X } from "lucide-react";
import type { MoleculeCandidate } from "./domain";
import { Molecule2D } from "./Molecule2D";
import Molecule3D from "./Molecule3D";

interface Props {
  dialogRef: RefObject<HTMLDialogElement | null>;
  molecule: MoleculeCandidate;
  sourceUrl: string | null;
  sourceFile: File | null;
  sourceHash: string | null;
  onReject: () => void;
  onEdit: () => void;
  onConfirm: () => void;
}

export function SourceReviewDialog({ dialogRef, molecule, sourceUrl, sourceFile, sourceHash, onReject, onEdit, onConfirm }: Props) {
  const matchesUploadedFile = molecule.manifest.mode === "live" && Boolean(sourceHash) && sourceHash === molecule.sourceFileSha256;
  return <dialog ref={dialogRef} className="source-dialog" aria-labelledby="source-dialog-title">
    <div className="modal-heading"><div><h2 id="source-dialog-title">Source confirmation desk</h2><p>Compare the source with the proposed molecular graph before accepting it.</p></div>
      <button className="modal-close" onClick={() => dialogRef.current?.close()} aria-label="Close source review"><X size={18} /></button></div>
    <div className="modal-source-grid">
      <section className="modal-source-pane" aria-label="Original source">
        <span className="modal-pane-label">SOURCE DOCUMENT</span>
        {matchesUploadedFile && sourceUrl && sourceFile?.type.startsWith("image/") ? <img src={sourceUrl} alt={`Uploaded source ${sourceFile.name}`} />
          : matchesUploadedFile && sourceUrl && sourceFile?.type === "application/pdf" ? <iframe src={sourceUrl} title={`Uploaded source ${sourceFile.name}`} />
            : <div className="paper-excerpt"><span>ILLUSTRATIVE ACADEMIC EXCERPT</span><h3>Figure 2: Representative examples of synthesized compounds</h3>
              <p>{molecule.label} · {molecule.source}</p><Molecule2D molecule={molecule} compact />
              <small>This is a mock source excerpt. It is not an extracted paper or proof of identity.</small></div>}
      </section>
      <section className="modal-candidate-pane" aria-label="Proposed chemical structure">
        <span className="modal-pane-label">UNTRUSTED CANDIDATE</span><h3>{molecule.label}</h3>
        <div className="modal-candidate-graph"><Molecule3D smiles={molecule.smiles} label={molecule.label} autorotate={false} showLabels resetSignal={0} zoom={0.9} compact /></div>
        <dl><div><dt>Proposed SMILES</dt><dd><code>{molecule.smiles}</code></dd></div><div><dt>Status</dt><dd>{molecule.status.toUpperCase()}</dd></div></dl>
        <p>Confirm only if the graph and transcription match the source. The demo values are illustrative.</p>
      </section>
    </div>
    <div className="modal-actions"><button className="button button--danger" onClick={onReject}><X size={16} /> Reject</button>
      <button className="button button--outline" onClick={onEdit}><Pencil size={16} /> Edit structure</button>
      <button className="button button--primary" onClick={onConfirm}><Check size={16} /> Confirm structure</button></div>
  </dialog>;
}
