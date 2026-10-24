import type { DescriptorRecord, MoleculeCandidate } from "./domain";

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
    status: invalid ? "NOT_COMPUTED" : "OUTSIDE_SNAPSHOT_COVERAGE",
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
      explanation: "Oxygen atom 7 has three bonds without a compatible formal charge. No property values were calculated for this structure.",
      whyItMatters: "In this example, three single bonds on neutral oxygen violate its expected valence. Calculating properties from this graph would be unreliable.",
      nextStep: "Review atom 7, its formal charge, and the three surrounding bonds against the source.",
    },
    steps: [], descriptors: records([null, null, null, null, null, null, null, null], true),
    manifest: demoManifest("DEMO-ROW-14"),
  },
];
