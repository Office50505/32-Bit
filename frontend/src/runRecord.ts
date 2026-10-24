import type { MoleculeCandidate } from "./domain";

export function createRunRecord(runId: string, molecules: MoleculeCandidate[]) {
  return {
    format: "provenancelab-run-v1",
    runId,
    note: "Demo records are illustrative; null hashes and toolkit versions are intentionally not fabricated. Reference coverage is stated per record.",
    records: molecules.map((molecule) => ({
      id: molecule.id,
      label: molecule.label,
      submittedSmiles: molecule.smiles,
      status: molecule.status,
      source: molecule.source,
      sourceFileSha256: molecule.sourceFileSha256 ?? null,
      issue: molecule.issue,
      standardizationSteps: molecule.steps,
      descriptors: molecule.descriptors,
      provenance: molecule.manifest,
    })),
  };
}
