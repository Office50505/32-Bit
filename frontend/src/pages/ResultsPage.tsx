import { useQuery } from "@tanstack/react-query";
import { Download, GitCompareArrows } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { analyzeBatch } from "../api/analysis";
import { Button } from "../components/atoms/Button";
import { Spinner } from "../components/atoms/Spinner";
import { RunTabs, type RunTab } from "../components/molecules/RunTabs";
import { RunDetailPanel } from "../components/organisms/RunDetailPanel";
import { ValidationWorkspace } from "../components/organisms/ValidationWorkspace";
import { AppShell } from "../components/templates/AppShell";
import { loadRunDraft } from "../utils/runDraft";
import type { AnalysisNavigationState } from "./AnalysisPage";

export default function ResultsPage() {
  const navigate = useNavigate();
  const { runId } = useParams();
  const molecules = useMemo(loadRunDraft, []);
  const [selectedIndex, setSelectedIndex] = useState(Math.max(0, molecules.length - 1));
  const [activeTab, setActiveTab] = useState<RunTab>("validation");
  const resultsQuery = useQuery({
    queryKey: ["analysis-batch", molecules],
    queryFn: ({ signal }) => analyzeBatch(molecules, signal),
    enabled: molecules.length > 0,
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
  });

  const results = resultsQuery.data?.results ?? [];
  const selected = results[Math.min(selectedIndex, Math.max(0, results.length - 1))];
  const validCount = results.filter((result) => result.status !== "invalid").length;
  const invalidCount = results.filter((result) => result.status === "invalid").length;
  const runMatchesRoute = !results.length || runId === results[0]?.analysis_id;

  const returnToInput = (intent: AnalysisNavigationState["intent"]) => {
    const draft = molecules[Math.min(selectedIndex, Math.max(0, molecules.length - 1))];
    navigate("/", { state: { draft, intent } satisfies AnalysisNavigationState });
  };

  const downloadRun = () => {
    if (!results.length) return;
    const blob = new Blob([JSON.stringify({ results }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${results[0]?.analysis_id ?? "provenancelab-run"}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <AppShell activeStep={2}>
      <header className="page-heading page-heading--results">
        <span className="run-id">{results[0]?.analysis_id ?? "NO ACTIVE RUN"}</span>
        <h1>{molecules.length ? "Validation complete" : "No analysis run found"}</h1>
        {molecules.length ? (
          <p>
            {results.length || molecules.length} structure{results.length === 1 ? "" : "s"} analyzed; {validCount} produced computable properties.
            {invalidCount ? ` ${invalidCount} require${invalidCount === 1 ? "s" : ""} attention before calculation.` : ""}
          </p>
        ) : (
          <p>This browser session does not contain a confirmed molecular input.</p>
        )}
      </header>

      {!molecules.length ? (
        <div className="empty-run" role="status">
          <strong>Start a new analysis</strong>
          <span>Enter and confirm a SMILES string before opening a run.</span>
          <Button variant="primary" onClick={() => navigate("/")}>Go to molecular input</Button>
        </div>
      ) : resultsQuery.isLoading ? (
        <div className="results-loading"><Spinner label="Validating molecules" /><strong>Validating molecular structures…</strong></div>
      ) : resultsQuery.error ? (
        <div className="api-error api-error--page" role="alert">
          <strong>Chemistry service unavailable</strong>
          <span>{resultsQuery.error.message}</span>
          <small>Start the FastAPI backend on port 8000. No result has been fabricated.</small>
          <Button onClick={() => navigate("/")}>Return to source</Button>
        </div>
      ) : selected && runMatchesRoute ? (
        <>
          <ValidationWorkspace
            results={results}
            selectedIndex={selectedIndex}
            onSelect={setSelectedIndex}
            onEditStructure={() => returnToInput("edit")}
            onReviewSource={() => returnToInput("review-source")}
          />
          <RunTabs active={activeTab} onChange={setActiveTab} />
          <RunDetailPanel activeTab={activeTab} results={results} selected={selected} />
          <div className="run-actions">
            <Button icon={<Download size={18} />} onClick={downloadRun}>Download run record</Button>
            {validCount ? (
              <Button
                variant="primary"
                icon={<GitCompareArrows size={18} />}
                onClick={() => setActiveTab("properties")}
              >
                {validCount > 1 ? "Compare valid structures" : "View computed properties"}
              </Button>
            ) : null}
          </div>
        </>
      ) : (
        <div className="empty-run" role="alert">
          <strong>This run identifier does not match the active session.</strong>
          <span>Run records are currently held in session storage and are not persisted on a server.</span>
          <Button variant="primary" onClick={() => navigate("/")}>Start a new analysis</Button>
        </div>
      )}
    </AppShell>
  );
}
