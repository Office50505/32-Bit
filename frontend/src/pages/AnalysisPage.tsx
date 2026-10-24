import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { useNavigate } from "react-router-dom";

import { analyzeMolecule } from "../api/analysis";
import { CandidatePanel } from "../components/organisms/CandidatePanel";
import { SourceWorkspace } from "../components/organisms/SourceWorkspace";
import { AppShell } from "../components/templates/AppShell";
import type { InputMode } from "../components/molecules/InputModeTab";
import { DEFAULT_CANDIDATE, DEMO_COMPARISON_INPUTS } from "../data/demo";
import { saveRunDraft } from "../utils/runDraft";

export default function AnalysisPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<InputMode>("paper");
  const [fileName, setFileName] = useState(DEFAULT_CANDIDATE.source?.filename ?? "paper_figure_2.pdf");
  const [structure, setStructure] = useState(DEFAULT_CANDIDATE.structure);
  const [label, setLabel] = useState(DEFAULT_CANDIDATE.label ?? "Candidate molecule");
  const deferredStructure = useDeferredValue(structure.trim());

  const candidateQuery = useQuery({
    queryKey: ["candidate-preview", deferredStructure, label],
    queryFn: ({ signal }) => analyzeMolecule({ structure: deferredStructure, label }, signal),
    enabled: deferredStructure.length > 0,
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
  });

  const confirmCandidate = () => {
    const confirmed = { structure, label, source: { filename: fileName, source_type: mode } };
    saveRunDraft([confirmed, DEMO_COMPARISON_INPUTS[1], DEMO_COMPARISON_INPUTS[2]]);
    navigate("/runs/current");
  };

  return (
    <AppShell activeStep={0}>
      <header className="page-heading">
        <h1>Start with your source</h1>
        <p>Upload the evidence you have. We’ll preserve the original and ask you to confirm every extracted structure.</p>
      </header>
      <div className="analysis-grid">
        <SourceWorkspace
          mode={mode}
          fileName={fileName}
          structure={structure}
          label={label}
          onModeChange={setMode}
          onFileSelect={(file) => setFileName(file.name)}
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
