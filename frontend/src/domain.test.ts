import { describe, expect, it } from "vitest";

import { moleculeDisplayLabel } from "./domain";

describe("moleculeDisplayLabel", () => {
  it("numbers backend-default labels using the run position", () => {
    expect(moleculeDisplayLabel({ label: "Untitled molecule", inputIndex: 2 })).toBe(
      "Structure 3",
    );
  });

  it("preserves an explicit user label", () => {
    expect(moleculeDisplayLabel({ label: "Aspirin", inputIndex: 0 })).toBe("Aspirin");
  });
});
