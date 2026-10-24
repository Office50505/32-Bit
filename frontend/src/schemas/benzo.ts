export interface BenzoStructureSuggestion {
  title: string;
  detail: string;
  smiles: string | null;
}

export interface BenzoChatResponse {
  scope: "ANSWERED" | "OUT_OF_SCOPE";
  answer: string;
  suggestions: BenzoStructureSuggestion[];
  model: string;
}
