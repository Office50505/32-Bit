export interface CsvMoleculeCandidate {
  label?: string;
  smiles: string;
}

const SMILES_HEADERS = new Set([
  "smiles",
  "canonicalsmiles",
  "isomericsmiles",
  "structure",
  "molecule",
  "molecularvalue",
]);

const LABEL_HEADERS = new Set(["label", "name", "compound", "compoundname", "moleculename"]);

function normalizeHeader(value: string) {
  return value.replace(/^\uFEFF/, "").trim().toLowerCase().replace(/[\s_-]+/g, "");
}

function parseRows(source: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (character === '"') {
      if (quoted && source[index + 1] === '"') {
        field += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === "," && !quoted) {
      row.push(field);
      field = "";
    } else if ((character === "\n" || character === "\r") && !quoted) {
      if (character === "\r" && source[index + 1] === "\n") index += 1;
      row.push(field);
      if (row.some((value) => value.trim())) rows.push(row);
      row = [];
      field = "";
    } else {
      field += character;
    }
  }

  if (quoted) throw new Error("The CSV contains an unclosed quoted value.");
  row.push(field);
  if (row.some((value) => value.trim())) rows.push(row);
  return rows;
}

export function parseCsvMolecule(source: string): CsvMoleculeCandidate {
  const rows = parseRows(source);
  if (rows.length < 2) {
    throw new Error("The CSV must include a header row and at least one molecule.");
  }

  const headers = rows[0].map(normalizeHeader);
  const smilesIndex = headers.findIndex((header) => SMILES_HEADERS.has(header));
  const labelIndex = headers.findIndex((header) => LABEL_HEADERS.has(header));
  if (smilesIndex < 0) {
    throw new Error('The CSV needs a column named "SMILES" or "structure".');
  }

  const candidateRow = rows.slice(1).find((candidate) => candidate[smilesIndex]?.trim());
  if (!candidateRow) throw new Error("The CSV does not contain a molecular value.");

  const label = labelIndex >= 0 ? candidateRow[labelIndex]?.trim() : "";
  return {
    smiles: candidateRow[smilesIndex].trim(),
    ...(label ? { label: label.slice(0, 200) } : {}),
  };
}
