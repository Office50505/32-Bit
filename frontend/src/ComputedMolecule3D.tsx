import { useEffect, useState } from "react";

import { getComputedConformer } from "./api/analysis";
import type { MoleculeStatus } from "./domain";
import Molecule3D from "./Molecule3D";
import type { Conformer3D } from "./schemas/analysis";

interface Props {
  structure?: string | null;
  label: string;
  status: MoleculeStatus;
  autorotate: boolean;
  resetSignal: number;
  zoom: number;
  compact?: boolean;
}

export function ComputedMolecule3D({
  structure,
  label,
  status,
  autorotate,
  resetSignal,
  zoom,
  compact = false,
}: Props) {
  const [conformer, setConformer] = useState<Conformer3D | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let current = true;
    setConformer(null);
    setError("");
    if (status !== "valid" || !structure) return () => { current = false; };
    void getComputedConformer(structure)
      .then((result) => {
        if (current) setConformer(result);
      })
      .catch((reason) => {
        if (current) setError(reason instanceof Error ? reason.message : "3D conformer unavailable.");
      });
    return () => { current = false; };
  }, [status, structure]);

  if (status === "invalid") {
    return <div className="computed-3d-state" role="status"><strong>3D unavailable</strong><span>Correct the invalid structure before generating coordinates.</span></div>;
  }
  if (status === "ambiguous") {
    return <div className="computed-3d-state" role="status"><strong>3D pending stereochemistry</strong><span>Confirm the missing stereochemical assignment first.</span></div>;
  }
  if (!structure) {
    return <div className="computed-3d-state" role="status"><strong>3D conformer unavailable</strong><span>No standardized parent structure is available for coordinate generation.</span></div>;
  }
  if (error) {
    return <div className="computed-3d-state" role="status"><strong>3D conformer unavailable</strong><span>{error}</span></div>;
  }
  if (!conformer) {
    return <div className="computed-3d-state computed-3d-state--loading" role="status"><strong>Building computed 3D conformer…</strong><span>RDKit ETKDG is generating coordinates on demand.</span></div>;
  }
  return <>
    <Molecule3D
      smiles={structure ?? ""}
      label={label}
      autorotate={autorotate}
      resetSignal={resetSignal}
      zoom={zoom}
      compact={compact}
      conformer={conformer}
    />
    {!compact ? <span className="viewer-watermark">Computed 3D · {conformer.method} · {conformer.coordinate_sha256.slice(0, 10)}…</span> : null}
  </>;
}
