export interface CsvMoleculeCandidate {
  label?: string;
  smiles: string;
  row: number;
  excerpt: string;
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

interface ParsedCsvRow {
  fields: string[];
  line: number;
}

function parseRows(source: string): ParsedCsvRow[] {
  const rows: ParsedCsvRow[] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  let line = 1;
  let rowStartLine = 1;

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
    } else if (character === "\n" || character === "\r") {
      const isCrLf = character === "\r" && source[index + 1] === "\n";
      if (quoted) {
        field += "\n";
      } else {
        row.push(field);
        if (row.some((value) => value.trim())) rows.push({ fields: row, line: rowStartLine });
        row = [];
        field = "";
        rowStartLine = line + 1;
      }
      if (isCrLf) index += 1;
      line += 1;
    } else {
      field += character;
    }
  }

  if (quoted) throw new Error("The CSV contains an unclosed quoted value.");
  row.push(field);
  if (row.some((value) => value.trim())) rows.push({ fields: row, line: rowStartLine });
  return rows;
}

export function parseCsvMolecules(source: string): CsvMoleculeCandidate[] {
  const rows = parseRows(source);
  if (rows.length < 2) {
    throw new Error("The CSV must include a header row and at least one molecule.");
  }

  const headers = rows[0].fields.map(normalizeHeader);
  const smilesIndex = headers.findIndex((header) => SMILES_HEADERS.has(header));
  const labelIndex = headers.findIndex((header) => LABEL_HEADERS.has(header));
  if (smilesIndex < 0) {
    throw new Error('The CSV needs a column named "SMILES" or "structure".');
  }

  const candidates = rows.slice(1).flatMap((candidateRow) => {
    const smiles = candidateRow.fields[smilesIndex]?.trim();
    if (!smiles) return [];
    const label = labelIndex >= 0 ? candidateRow.fields[labelIndex]?.trim() : "";
    return [{
      smiles,
      row: candidateRow.line,
      excerpt: candidateRow.fields.join(",").slice(0, 600),
      ...(label ? { label: label.slice(0, 200) } : {}),
    }];
  });
  if (!candidates.length) throw new Error("The CSV does not contain a molecular value.");
  return candidates;
}

export function parseCsvMolecule(source: string): CsvMoleculeCandidate {
  return parseCsvMolecules(source)[0];
}
