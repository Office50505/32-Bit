import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Spinner } from "./components/atoms/Spinner";
import AnalysisPage from "./pages/AnalysisPage";

const ResultsPage = lazy(() => import("./pages/ResultsPage"));

export default function App() {
  return (
    <Suspense fallback={<div className="route-loading"><Spinner label="Loading page" /></div>}>
      <Routes>
        <Route path="/" element={<AnalysisPage />} />
        <Route path="/runs/:runId" element={<ResultsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
