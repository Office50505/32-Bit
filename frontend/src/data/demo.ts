import type { AnalyzeRequest } from "../schemas/analysis";

export const DEFAULT_CANDIDATE: AnalyzeRequest = {
  label: "Aspirin candidate",
  structure: "CC(=O)Oc1ccccc1C(=O)O",
  source: {
    filename: "paper_figure_2.pdf",
    source_type: "paper",
    page: 3,
  },
};

export const DEMO_COMPARISON_INPUTS: AnalyzeRequest[] = [
  {
    label: "Aspirin",
    structure: "CC(=O)Oc1ccccc1C(=O)O",
    source: { filename: "paper_figure_2.pdf", source_type: "paper", page: 3 },
  },
  {
    label: "2-butanol",
    structure: "CCC(O)C",
    source: { filename: "lecture_notes.png", source_type: "image" },
  },
  {
    label: "Source row 14",
    structure: "C[O](C)C",
    source: { filename: "student_compounds.csv", source_type: "csv" },
  },
];

export const RUN_DRAFT_STORAGE_KEY = "provenancelab.run-draft.v1";
