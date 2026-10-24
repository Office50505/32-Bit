import { describe, expect, it } from "vitest";

import { parseCsvMolecule } from "./csvMolecule";

describe("parseCsvMolecule", () => {
  it("reads a named molecule from a SMILES column", () => {
    expect(parseCsvMolecule("name,SMILES\nAspirin,CC(=O)Oc1ccccc1C(=O)O\n")).toEqual({
      label: "Aspirin",
      smiles: "CC(=O)Oc1ccccc1C(=O)O",
    });
  });

  it("supports BOM-prefixed headers and quoted labels", () => {
    expect(parseCsvMolecule('\uFEFFcompound name,canonical_smiles\n"Example, molecule",CCO')).toEqual({
      label: "Example, molecule",
      smiles: "CCO",
    });
  });

  it("explains when a molecular column is missing", () => {
    expect(() => parseCsvMolecule("name,formula\nWater,H2O")).toThrow(
      'The CSV needs a column named "SMILES" or "structure".',
    );
  });
});
