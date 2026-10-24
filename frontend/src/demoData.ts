import type { Atom3D, Bond3D, DescriptorRecord, MoleculeCandidate } from "./domain";

const unavailable = "This property is outside the small bootstrap demo dataset. No claim is made about PubChem or ChEMBL.";
const labels = [
  ["molecular_formula", "Molecular formula", ""],
  ["molecular_weight", "Molecular weight", "g/mol"],
  ["exact_mass", "Exact mass", "Da"],
  ["logp", "LogP", ""],
  ["tpsa", "Topological polar surface area", "Å²"],
  ["hbd", "H-bond donors", ""],
  ["hba", "H-bond acceptors", ""],
  ["rotatable_bonds", "Rotatable bonds", ""],
] as const;

function records(values: readonly (string | number | null)[], invalid = false): DescriptorRecord[] {
  return labels.map(([key, label, unit], index) => ({
    key,
    label,
    value: values[index],
    unit: unit || undefined,
    reference: null,
    status: invalid ? "NOT_COMPUTED" : "OUTSIDE_COVERAGE",
    reason: invalid ? "Invalid structure blocked every descriptor calculation." : unavailable,
  }));
}

const demoManifest = (id: string) => ({
  analysisId: id,
  inputSha256: null,
  outputSha256: null,
  configurationSha256: null,
  rdkitVersion: null,
  snapshotId: "demo-bootstrap-v1",
  mode: "demo" as const,
});

const aspirinRecords = records(["C9H8O4", 180.16, 180.0423, 1.31, 63.6, 1, 4, 3]).map((record) => {
  if (record.key === "molecular_formula") return { ...record, reference: "C9H8O4", status: "MATCH" as const, reason: "Synthetic bootstrap reference matches the illustrative calculated formula." };
  if (record.key === "molecular_weight") return { ...record, reference: 180.16, status: "MATCH" as const, reason: "Synthetic bootstrap reference matches within the example tolerance." };
  if (record.key === "logp") return { ...record, reference: 1.55, status: "DIFFERENCE" as const, reason: "Synthetic bootstrap reference differs from the illustrative computed value; this is a demonstration flag." };
  if (record.key === "exact_mass") return { ...record, status: "NOT_AVAILABLE" as const, reason: "This compound is in the synthetic bootstrap dataset, but exact mass was not recorded." };
  return record;
});

export const DEMO_MOLECULES: MoleculeCandidate[] = [
  {
    id: "aspirin", label: "Aspirin", smiles: "CC(=O)Oc1ccccc1C(=O)O", formula: "C₉H₈O₄", weight: 180.16,
    status: "valid", source: "Demo figure 2 · compound 1", confirmed: true,
    issue: null,
    steps: [
      { code: "CLEANUP", label: "Normalize functional groups", before: "CC(=O)Oc1ccccc1C(=O)O", after: "CC(=O)Oc1ccccc1C(=O)O", changed: false },
      { code: "FRAGMENT_PARENT", label: "Select parent fragment", before: "CC(=O)Oc1ccccc1C(=O)O", after: "CC(=O)Oc1ccccc1C(=O)O", changed: false },
    ],
    descriptors: aspirinRecords,
    manifest: demoManifest("DEMO-ASPIRIN"),
  },
  {
    id: "compound-7b", label: "Compound 7b", smiles: "CCC(O)C", formula: "C₄H₁₀O", weight: 74.12,
    status: "ambiguous", source: "Demo scheme 1 · compound 7b", confirmed: true,
    issue: {
      code: "UNSPECIFIED_STEREOCHEMISTRY", title: "Ambiguous stereochemistry", severity: "warning", atomIndex: 2,
      explanation: "The stereogenic carbon has no assigned configuration. The SMILES does not distinguish its possible enantiomers.",
      whyItMatters: "Different stereoisomers can have different biological activity. The structure must not be treated as a unique stereoisomer.",
      nextStep: "Check the source for wedge bonds or an explicit stereochemical identifier before assigning @ or @@.",
    },
    steps: [{ code: "CLEANUP", label: "Normalize functional groups", before: "CCC(O)C", after: "CCC(O)C", changed: false }],
    descriptors: records(["C4H10O", 74.12, 74.0732, 0.81, 20.23, 1, 1, 1]),
    manifest: demoManifest("DEMO-COMPOUND-7B"),
  },
  {
    id: "source-row-14", label: "Source row 14", smiles: "CCCCCC[O](C)C", formula: null, weight: null,
    status: "invalid", source: "Demo table 2 · row 14", confirmed: true,
    issue: {
      code: "IMPOSSIBLE_VALENCE", title: "Impossible valence", severity: "error", atomIndex: 6,
      explanation: "Oxygen atom 7 has three single bonds without a compatible formal charge. No properties were calculated.",
      whyItMatters: "The notation cannot be accepted as a chemically valid molecular graph, so a property value would be misleading.",
      nextStep: "Review atom 7, its formal charge, and the three surrounding bonds against the source.",
    },
    steps: [], descriptors: records([null, null, null, null, null, null, null, null], true),
    manifest: demoManifest("DEMO-ROW-14"),
  },
];

export const DEMO_GEOMETRY: Record<string, { atoms: Atom3D[]; bonds: Bond3D[] }> = {
  aspirin: {
    atoms: [
      { element: "C", position: [-1.5, 1, 0] }, { element: "C", position: [-0.4, 1.6, 0] },
      { element: "C", position: [0.8, 1, 0] }, { element: "C", position: [0.8, -0.4, 0] },
      { element: "C", position: [-0.4, -1, 0] }, { element: "C", position: [-1.5, -0.4, 0] },
      { element: "O", position: [-2.6, 1.7, 0.2] }, { element: "C", position: [-3.8, 1.2, 0.3] },
      { element: "O", position: [-4.6, 2.1, 0.3] }, { element: "C", position: [-4.1, -0.1, 0.4] },
      { element: "C", position: [2.1, 1.7, 0.2] }, { element: "O", position: [3.2, 1.1, 0.2] },
      { element: "O", position: [2.1, 3, 0.2] },
    ],
    bonds: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 0], [0, 6], [6, 7], [7, 8], [7, 9], [2, 10], [10, 11], [10, 12]].map(([from, to]) => ({ from, to })),
  },
  "compound-7b": {
    atoms: [
      { element: "C", position: [-2, -0.3, 0] }, { element: "C", position: [-0.8, 0.4, 0] },
      { element: "C", position: [0.5, -0.2, 0] }, { element: "O", position: [1, 1.1, 0.3] },
      { element: "C", position: [1.7, -0.9, 0] },
    ],
    bonds: [[0, 1], [1, 2], [2, 3], [2, 4]].map(([from, to]) => ({ from, to })),
  },
  "source-row-14": {
    atoms: Array.from({ length: 9 }, (_, index) => ({ element: index === 6 ? "O" as const : "C" as const, position: [index < 7 ? index * 0.8 - 2.5 : 2.2, index < 7 ? (index % 2) * 0.45 : index === 7 ? 1.5 : -1, 0] as [number, number, number] })),
    bonds: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7], [6, 8]].map(([from, to]) => ({ from, to })),
  },
};
