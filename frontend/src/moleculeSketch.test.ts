import { describe, expect, it } from "vitest";

import { parseSmilesSketch } from "./moleculeSketch";

describe("parseSmilesSketch", () => {
  it("reconstructs aromatic ring connectivity", () => {
    const result = parseSmilesSketch("c1ccccc1");

    expect(result.error).toBeUndefined();
    expect(result.model?.atoms).toHaveLength(6);
    expect(result.model?.bonds).toHaveLength(6);
    expect(result.model?.ringCount).toBe(1);
  });

  it("preserves branches and double bonds", () => {
    const result = parseSmilesSketch("CC(=O)Oc1ccccc1C(=O)O");

    expect(result.error).toBeUndefined();
    expect(result.model?.atoms).toHaveLength(13);
    expect(result.model?.bonds.some((item) => item.order === 2)).toBe(true);
  });

  it("flags the valence conflict in the invalid demo", () => {
    const result = parseSmilesSketch("CCCCCC[O](C)C");

    expect(result.error).toBeUndefined();
    expect(result.model?.valenceIssues).toEqual([
      expect.objectContaining({ atomIndex: 6, element: "O", observed: 3, expected: 2 }),
    ]);
  });

  it("returns a useful error for an unclosed branch", () => {
    const result = parseSmilesSketch("CC(O");

    expect(result.error).toBe("Unclosed branch");
    expect(result.model).toBeUndefined();
  });
});
