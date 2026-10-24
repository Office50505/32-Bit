import type { RefObject } from "react";
import { Download, X } from "lucide-react";
import type { createRunRecord } from "./runRecord";

interface Props {
  dialogRef: RefObject<HTMLDialogElement | null>;
  record: ReturnType<typeof createRunRecord>;
  onDownload: () => void;
}

export function RunRecordDialog({ dialogRef, record, onDownload }: Props) {
  return <dialog ref={dialogRef} className="record-dialog" aria-labelledby="record-dialog-title">
    <div className="modal-heading"><div><h2 id="record-dialog-title">Run provenance record</h2><p>Review the JSON manifest before downloading.</p></div>
      <button className="modal-close" onClick={() => dialogRef.current?.close()} aria-label="Close run record"><X size={18} /></button></div>
    <p className="modal-notice">Illustrative records intentionally have null SHA-256 and RDKit fields. Live results carry values returned by the backend.</p>
    <pre className="manifest-json">{JSON.stringify(record, null, 2)}</pre>
    <div className="modal-actions"><button className="button button--outline" onClick={() => dialogRef.current?.close()}>Close</button>
      <button className="button button--primary" onClick={onDownload}><Download size={16} /> Download JSON</button></div>
  </dialog>;
}
