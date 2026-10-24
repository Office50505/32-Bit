import { describe, expect, it } from "vitest";

import { parseCsvMolecule, parseCsvMolecules } from "./csvMolecule";

describe("parseCsvMolecule", () => {
  it("reads a named molecule from a SMILES column", () => {
    expect(parseCsvMolecule("name,SMILES\nAspirin,CC(=O)Oc1ccccc1C(=O)O\n")).toEqual({
      label: "Aspirin",
      smiles: "CC(=O)Oc1ccccc1C(=O)O",
      row: 2,
      excerpt: "Aspirin,CC(=O)Oc1ccccc1C(=O)O",
    });
  });

  it("supports BOM-prefixed headers and quoted labels", () => {
    expect(parseCsvMolecule('\uFEFFcompound name,canonical_smiles\n"Example, molecule",CCO')).toEqual({
      label: "Example, molecule",
      smiles: "CCO",
      row: 2,
      excerpt: "Example, molecule,CCO",
    });
  });

  it("returns every populated molecule row with row provenance", () => {
    expect(parseCsvMolecules("name,smiles\nEthanol,CCO\n\nBenzene,c1ccccc1\n")).toEqual([
      { label: "Ethanol", smiles: "CCO", row: 2, excerpt: "Ethanol,CCO" },
      { label: "Benzene", smiles: "c1ccccc1", row: 4, excerpt: "Benzene,c1ccccc1" },
    ]);
  });

  it("keeps the starting line for multiline CSV records", () => {
    expect(parseCsvMolecules('name,smiles,notes\nEthanol,CCO,"first line\nsecond line"\nBenzene,c1ccccc1,ring'))
      .toEqual([
        { label: "Ethanol", smiles: "CCO", row: 2, excerpt: "Ethanol,CCO,first line\nsecond line" },
        { label: "Benzene", smiles: "c1ccccc1", row: 4, excerpt: "Benzene,c1ccccc1,ring" },
      ]);
  });

  it("explains when a molecular column is missing", () => {
    expect(() => parseCsvMolecule("name,formula\nWater,H2O")).toThrow(
      'The CSV needs a column named "SMILES" or "structure".',
    );
  });
});
