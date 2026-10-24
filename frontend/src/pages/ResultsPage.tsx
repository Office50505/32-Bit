import { useQuery } from "@tanstack/react-query";
import { Download, GitCompareArrows } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { analyzeBatch } from "../api/analysis";
import { Button } from "../components/atoms/Button";
import { Spinner } from "../components/atoms/Spinner";
import { RunTabs, type RunTab } from "../components/molecules/RunTabs";
import { RunDetailPanel } from "../components/organisms/RunDetailPanel";
import { ValidationWorkspace } from "../components/organisms/ValidationWorkspace";
import { AppShell } from "../components/templates/AppShell";
import { loadRunDraft } from "../utils/runDraft";

export default function ResultsPage() {
  const navigate = useNavigate();
  const molecules = useMemo(loadRunDraft, []);
  const [selectedIndex, setSelectedIndex] = useState(Math.max(0, molecules.length - 1));
  const [activeTab, setActiveTab] = useState<RunTab>("validation");
  const resultsQuery = useQuery({
    queryKey: ["analysis-batch", molecules],
    queryFn: ({ signal }) => analyzeBatch(molecules, signal),
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
  });

  const results = resultsQuery.data?.results ?? [];
  const selected = results[Math.min(selectedIndex, Math.max(0, results.length - 1))];
  const validCount = results.filter((result) => result.status !== "invalid").length;
  const invalidCount = results.filter((result) => result.status === "invalid").length;

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
        <span className="run-id">{results[0]?.analysis_id ?? "RUN PENDING"}</span>
        <h1>Validation complete</h1>
        <p>
          {validCount || 0} structure{validCount === 1 ? " is" : "s are"} ready to compare.
          {invalidCount ? ` ${invalidCount} need${invalidCount === 1 ? "s" : ""} attention before properties can be calculated.` : ""}
        </p>
      </header>

      {resultsQuery.isLoading ? (
        <div className="results-loading"><Spinner label="Validating molecules" /><strong>Validating molecular structures…</strong></div>
      ) : resultsQuery.error ? (
        <div className="api-error api-error--page" role="alert">
          <strong>Chemistry service unavailable</strong>
          <span>{resultsQuery.error.message}</span>
          <small>Start the FastAPI backend on port 8000. No result has been fabricated.</small>
          <Button onClick={() => navigate("/")}>Return to source</Button>
        </div>
      ) : selected ? (
        <>
          <ValidationWorkspace
            results={results}
            selectedIndex={selectedIndex}
            onSelect={setSelectedIndex}
            onReviewSource={() => navigate("/")}
          />
          <RunTabs active={activeTab} onChange={setActiveTab} />
          <RunDetailPanel activeTab={activeTab} results={results} selected={selected} />
          <div className="run-actions">
            <Button icon={<Download size={18} />} onClick={downloadRun}>Download run record</Button>
            <Button
              variant="primary"
              icon={<GitCompareArrows size={18} />}
              onClick={() => setActiveTab("properties")}
            >
              Compare valid structures
            </Button>
          </div>
        </>
      ) : null}
    </AppShell>
  );
}
