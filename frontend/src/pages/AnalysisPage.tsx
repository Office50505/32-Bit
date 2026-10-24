import { useQuery } from "@tanstack/react-query";
import { useCallback, useDeferredValue, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { analyzeMolecule } from "../api/analysis";
import { CandidatePanel } from "../components/organisms/CandidatePanel";
import { SourceWorkspace } from "../components/organisms/SourceWorkspace";
import { AppShell } from "../components/templates/AppShell";
import type { InputMode } from "../components/molecules/InputModeTab";
import type { AnalyzeRequest } from "../schemas/analysis";
import { createPhotoSource, loadPhotoSource, type PhotoSourceDraft } from "../utils/photoSource";
import { saveRunDraft } from "../utils/runDraft";

export interface AnalysisNavigationState {
  draft?: AnalyzeRequest;
  intent?: "edit" | "review-source";
}

export default function AnalysisPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const restoredState = location.state as AnalysisNavigationState | null;
  const restoredDraft = restoredState?.draft;
  const restoredSourceType = restoredDraft?.source?.source_type;
  const restoredPhoto = useMemo(
    () => loadPhotoSource(restoredDraft?.source?.file_sha256),
    [restoredDraft?.source?.file_sha256],
  );
  const [mode, setMode] = useState<InputMode>(() => restoredSourceType === "photo" ? "photo" : "data");
  const [structure, setStructure] = useState(() => restoredDraft?.structure ?? "");
  const [label, setLabel] = useState(() => restoredDraft?.label ?? "");
  const [photo, setPhoto] = useState<PhotoSourceDraft | null>(() => restoredPhoto);
  const [photoError, setPhotoError] = useState<string | null>(() => {
    if (restoredSourceType === "photo" && !restoredPhoto) {
      return "The original image is no longer available in this browser session. Choose it again to preserve the source preview.";
    }
    return null;
  });
  const [isPhotoReading, setIsPhotoReading] = useState(false);
  const deferredStructure = useDeferredValue(structure.trim());
  const normalizedLabel = label.trim();
  const source = useMemo(() => {
    if (mode !== "photo") {
      return { source_type: "direct-smiles" };
    }
    if (!photo) return { source_type: "photo" };
    return {
      source_type: "photo",
      filename: photo.filename,
      media_type: photo.mediaType,
      file_size: photo.fileSize,
      file_sha256: photo.sha256,
      extraction_method: "manual-smiles-transcription",
    };
  }, [mode, photo]);
  const canPreview = deferredStructure.length > 0 && (mode !== "photo" || Boolean(photo));

  const handlePhotoSelect = useCallback(async (file: File) => {
    setIsPhotoReading(true);
    setPhotoError(null);
    try {
      setPhoto(await createPhotoSource(file));
    } catch (error) {
      setPhoto(null);
      setPhotoError(error instanceof Error ? error.message : "The selected image could not be read.");
    } finally {
      setIsPhotoReading(false);
    }
  }, []);

  const candidateQuery = useQuery({
    queryKey: ["candidate-preview", deferredStructure, normalizedLabel, source],
    queryFn: ({ signal }) => analyzeMolecule({
      structure: deferredStructure,
      label: normalizedLabel || undefined,
      source,
    }, signal),
    enabled: canPreview,
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
  });

  const confirmCandidate = () => {
    if (!candidateQuery.data) return;
    const confirmed = {
      structure: structure.trim(),
      label: normalizedLabel || undefined,
      source,
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
          photo={photo}
          photoError={photoError}
          isPhotoReading={isPhotoReading}
          autoFocusStructure={Boolean(restoredDraft)}
          onModeChange={setMode}
          onStructureChange={setStructure}
          onLabelChange={setLabel}
          onPhotoSelect={handlePhotoSelect}
        />
        <CandidatePanel
          candidate={candidateQuery.data}
          isLoading={candidateQuery.isLoading || candidateQuery.isFetching}
          error={candidateQuery.error}
          onConfirm={confirmCandidate}
          onEdit={() => setMode("data")}
          onReject={() => {
            setStructure("");
            setLabel("");
            setPhoto(null);
            setPhotoError(null);
            setMode("data");
          }}
        />
      </div>
    </AppShell>
  );
}
