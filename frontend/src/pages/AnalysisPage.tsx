import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { useNavigate } from "react-router-dom";

import { analyzeMolecule } from "../api/analysis";
import { CandidatePanel } from "../components/organisms/CandidatePanel";
import { SourceWorkspace } from "../components/organisms/SourceWorkspace";
import { AppShell } from "../components/templates/AppShell";
import type { InputMode } from "../components/molecules/InputModeTab";
import { saveRunDraft } from "../utils/runDraft";

export default function AnalysisPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<InputMode>("data");
  const [structure, setStructure] = useState("");
  const [label, setLabel] = useState("");
  const deferredStructure = useDeferredValue(structure.trim());
  const normalizedLabel = label.trim();

  const candidateQuery = useQuery({
    queryKey: ["candidate-preview", deferredStructure, normalizedLabel],
    queryFn: ({ signal }) => analyzeMolecule({
      structure: deferredStructure,
      label: normalizedLabel || undefined,
      source: { source_type: "direct-smiles" },
    }, signal),
    enabled: deferredStructure.length > 0,
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
  });

  const confirmCandidate = () => {
    if (!candidateQuery.data) return;
    const confirmed = {
      structure: structure.trim(),
      label: normalizedLabel || undefined,
      source: { source_type: "direct-smiles" },
    };
    saveRunDraft([confirmed]);
    navigate(`/runs/${candidateQuery.data.analysis_id}`);
  };

  return (
    <AppShell activeStep={0}>
      <header className="page-heading">
        <h1>Validate a molecular structure</h1>
        <p>Enter a SMILES string to inspect validity, ambiguity, standardization, calculated properties, and provenance.</p>
      </header>
      <div className="analysis-grid">
        <SourceWorkspace
          mode={mode}
          structure={structure}
          label={label}
          onModeChange={setMode}
          onStructureChange={setStructure}
          onLabelChange={setLabel}
        />
        <CandidatePanel
          candidate={candidateQuery.data}
          isLoading={candidateQuery.isLoading || candidateQuery.isFetching}
          error={candidateQuery.error}
          onConfirm={confirmCandidate}
          onEdit={() => setMode("data")}
          onReject={() => {
            setStructure("");
            setMode("data");
          }}
        />
      </div>
    </AppShell>
  );
}
