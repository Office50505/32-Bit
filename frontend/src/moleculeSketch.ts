export interface SketchAtom {
  element: string;
  x: number;
  y: number;
  z: number;
  aromatic: boolean;
  charge: number;
  stereo: boolean;
  sourceToken: string;
  sourceStart: number;
  sourceEnd: number;
}

export interface SketchBond {
  a: number;
  b: number;
  order: number;
}

export interface ValenceIssue {
  atomIndex: number;
  element: string;
  observed: number;
  expected: number;
  sourceToken: string;
}

export interface MoleculeSketch {
  atoms: SketchAtom[];
  bonds: SketchBond[];
  viewSize: number;
  atomScale: number;
  ringCount: number;
  stereoCount: number;
  valenceIssues: ValenceIssue[];
}

export type SketchResult =
  | { model: MoleculeSketch; error?: never }
  | { model?: never; error: string };

export interface ElementStyle {
  color: string;
  edge: string;
  shade: string;
  radius: number;
  valence?: number;
}

export const ELEMENT_STYLES: Record<string, ElementStyle> = {
  H: { color: "#e9f0ef", edge: "#ffffff", shade: "#9caaad", radius: 12, valence: 1 },
  B: { color: "#d99577", edge: "#ffe2d4", shade: "#7f4834", radius: 18, valence: 3 },
  C: { color: "#607985", edge: "#c9d9dc", shade: "#203843", radius: 20, valence: 4 },
  N: { color: "#4274cf", edge: "#c8d8ff", shade: "#183b7c", radius: 19, valence: 3 },
  O: { color: "#cf3042", edge: "#ffc2ca", shade: "#781725", radius: 19, valence: 2 },
  F: { color: "#3aa967", edge: "#c9f6d7", shade: "#17613a", radius: 17, valence: 1 },
  Si: { color: "#a78b6e", edge: "#eadaca", shade: "#5d4937", radius: 22, valence: 4 },
  P: { color: "#d57a22", edge: "#ffd7aa", shade: "#79400d", radius: 22, valence: 3 },
  S: { color: "#c49112", edge: "#ffedaa", shade: "#69500b", radius: 22, valence: 2 },
  Cl: { color: "#239451", edge: "#c4f4d2", shade: "#105a2d", radius: 22, valence: 1 },
  Br: { color: "#9a503d", edge: "#ecc1b4", shade: "#54281f", radius: 24, valence: 1 },
  I: { color: "#7356ad", edge: "#d9cdf0", shade: "#3d2867", radius: 25, valence: 1 },
};

export const FALLBACK_ELEMENT_STYLE: ElementStyle = {
  color: "#788b94",
  edge: "#d7e1e4",
  shade: "#344851",
  radius: 21,
};

const AROMATIC_ELEMENTS = new Set(["b", "c", "n", "o", "p", "s"]);
const ORGANIC_ELEMENTS = new Set(["B", "C", "N", "O", "P", "S", "F", "I"]);

function layoutAtoms(atoms: SketchAtom[], bonds: SketchBond[]) {
  const positions: { x: number; y: number; z: number }[] = [];
  atoms.forEach((item, index) => {
    if (index === 0) {
      positions.push({ x: 0, y: 0, z: 0 });
      return;
    }
    const parentBond = bonds.find((candidate) => candidate.b === index && candidate.a < index)
      ?? bonds.find((candidate) => candidate.a === index && candidate.b < index);
    const parent = parentBond ? Math.min(parentBond.a, parentBond.b) : index - 1;
    const base = positions[parent] ?? { x: 0, y: 0, z: 0 };
    const angle = index * 2.399963 + parent * 0.61;
    positions.push({
      x: base.x + Math.cos(angle) * 1.2,
      y: base.y + Math.sin(angle) * 1.2,
      z: Math.sin(index * 1.73) * 0.52 + (item.stereo ? 0.45 : 0),
    });
  });

  const linked = new Set(bonds.map((item) => `${Math.min(item.a, item.b)}:${Math.max(item.a, item.b)}`));
  for (let iteration = 0; iteration < 190; iteration += 1) {
    const forces = positions.map(() => ({ x: 0, y: 0, z: 0 }));
    for (let first = 0; first < positions.length; first += 1) {
      for (let second = first + 1; second < positions.length; second += 1) {
        const dx = positions[second].x - positions[first].x;
        const dy = positions[second].y - positions[first].y;
        const dz = positions[second].z - positions[first].z;
        const distanceSquared = dx * dx + dy * dy + dz * dz + 0.08;
        const distance = Math.sqrt(distanceSquared);
        const strength = (linked.has(`${first}:${second}`) ? 0.006 : 0.052) / distanceSquared;
        const fx = (dx / distance) * strength;
        const fy = (dy / distance) * strength;
        const fz = (dz / distance) * strength;
        forces[first].x -= fx;
        forces[first].y -= fy;
        forces[first].z -= fz;
        forces[second].x += fx;
        forces[second].y += fy;
        forces[second].z += fz;
      }
    }

    bonds.forEach((item) => {
      const start = positions[item.a];
      const end = positions[item.b];
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const dz = end.z - start.z;
      const distance = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
      const target = item.order >= 2 ? 1.12 : 1.28;
      const strength = (distance - target) * 0.055;
      const fx = (dx / distance) * strength;
      const fy = (dy / distance) * strength;
      const fz = (dz / distance) * strength;
      forces[item.a].x += fx;
      forces[item.a].y += fy;
      forces[item.a].z += fz;
      forces[item.b].x -= fx;
      forces[item.b].y -= fy;
      forces[item.b].z -= fz;
    });

    positions.forEach((point, index) => {
      forces[index].x -= point.x * 0.0015;
      forces[index].y -= point.y * 0.0015;
      forces[index].z -= point.z * 0.001;
      const magnitude = Math.hypot(forces[index].x, forces[index].y, forces[index].z) || 1;
      const scale = Math.min(0.16, magnitude) / magnitude;
      point.x += forces[index].x * scale;
      point.y += forces[index].y * scale;
      point.z += forces[index].z * scale;
    });
  }

  const center = positions.reduce(
    (sum, point) => ({ x: sum.x + point.x, y: sum.y + point.y, z: sum.z + point.z }),
    { x: 0, y: 0, z: 0 },
  );
  center.x /= positions.length || 1;
  center.y /= positions.length || 1;
  center.z /= positions.length || 1;
  return positions.map((point) => ({
    x: point.x - center.x,
    y: point.y - center.y,
    z: point.z - center.z,
  }));
}

function chargeFromToken(content: string) {
  const token = content.match(/([+-]{1,3}|[+-]\d+)/)?.[1] ?? "";
  if (token.startsWith("+")) return Number(token.slice(1) || token.length);
  if (token.startsWith("-")) return -Number(token.slice(1) || token.length);
  return 0;
}

export function parseSmilesSketch(rawSmiles: string): SketchResult {
  const smiles = rawSmiles.trim().replace(/\\([()])/g, "$1").replace(/\s+/g, "");
  const atoms: SketchAtom[] = [];
  const bonds: SketchBond[] = [];
  const branches: number[] = [];
  const rings = new Map<string, { atom: number; order: number }>();
  let current = -1;
  let pendingOrder = 1;
  let pendingExplicit = false;
  let ringCount = 0;
  let stereoCount = 0;

  const addAtom = (raw: string, bracketed: boolean, sourceStart: number) => {
    const content = bracketed ? raw.slice(1, -1) : raw;
    const match = content.match(/^(?:\d+)?([A-Z][a-z]?|[bcnops])/);
    if (!match) throw new Error(`Unsupported atom token ${raw}`);
    const sourceElement = match[1];
    const aromatic = AROMATIC_ELEMENTS.has(sourceElement);
    const element = aromatic ? sourceElement.toUpperCase() : sourceElement;
    const stereo = content.includes("@");
    if (stereo) stereoCount += 1;
    const index = atoms.length;
    atoms.push({
      element,
      x: 0,
      y: 0,
      z: 0,
      aromatic,
      charge: chargeFromToken(content),
      stereo,
      sourceToken: raw,
      sourceStart,
      sourceEnd: sourceStart + raw.length,
    });
    if (current >= 0) {
      const previous = atoms[current];
      const order = !pendingExplicit && previous.aromatic && aromatic ? 1.5 : pendingOrder;
      bonds.push({ a: current, b: index, order });
    }
    current = index;
    pendingOrder = 1;
    pendingExplicit = false;
  };

  try {
    for (let index = 0; index < smiles.length;) {
      const character = smiles[index];
      if (character === "[") {
        const close = smiles.indexOf("]", index + 1);
        if (close < 0) throw new Error("Unclosed bracket atom");
        addAtom(smiles.slice(index, close + 1), true, index);
        index = close + 1;
        continue;
      }
      if (character === "(") {
        if (current < 0) throw new Error("Branch has no parent atom");
        branches.push(current);
        index += 1;
        continue;
      }
      if (character === ")") {
        const parent = branches.pop();
        if (parent === undefined) throw new Error("Unmatched closing branch");
        current = parent;
        index += 1;
        continue;
      }
      if ("-=#:/\\".includes(character)) {
        pendingOrder = character === "=" ? 2 : character === "#" ? 3 : character === ":" ? 1.5 : 1;
        pendingExplicit = true;
        index += 1;
        continue;
      }
      if (character === ".") {
        current = -1;
        index += 1;
        continue;
      }
      if (/\d/.test(character) || character === "%") {
        if (current < 0) throw new Error("Ring closure has no atom");
        const key = character === "%" ? smiles.slice(index + 1, index + 3) : character;
        if (!key || (character === "%" && !/^\d{2}$/.test(key))) throw new Error("Invalid ring closure");
        const opening = rings.get(key);
        if (opening) {
          bonds.push({ a: opening.atom, b: current, order: pendingExplicit ? pendingOrder : opening.order });
          rings.delete(key);
          ringCount += 1;
        } else {
          rings.set(key, { atom: current, order: pendingOrder });
        }
        pendingOrder = 1;
        pendingExplicit = false;
        index += character === "%" ? 3 : 1;
        continue;
      }

      const twoCharacter = smiles.slice(index, index + 2);
      if (twoCharacter === "Cl" || twoCharacter === "Br") {
        addAtom(twoCharacter, false, index);
        index += 2;
        continue;
      }
      if (ORGANIC_ELEMENTS.has(character) || AROMATIC_ELEMENTS.has(character)) {
        addAtom(character, false, index);
        index += 1;
        continue;
      }
      throw new Error(`Unexpected character “${character}”`);
    }
    if (branches.length) throw new Error("Unclosed branch");
    if (rings.size) throw new Error("Unclosed ring index");
    if (!atoms.length) throw new Error("No atoms found");
    if (atoms.length > 96) throw new Error("The interactive renderer supports up to 96 explicit atoms");
  } catch (error) {
    return { error: error instanceof Error ? error.message : "The SMILES input could not be rendered" };
  }

  const positions = layoutAtoms(atoms, bonds);
  atoms.forEach((item, index) => Object.assign(item, positions[index]));
  const bondLoad = new Array<number>(atoms.length).fill(0);
  bonds.forEach((item) => {
    bondLoad[item.a] += item.order;
    bondLoad[item.b] += item.order;
  });
  const valenceIssues: ValenceIssue[] = [];
  atoms.forEach((item, atomIndex) => {
    let allowed = ELEMENT_STYLES[item.element]?.valence;
    if (item.element === "N" && item.charge > 0) allowed = 4;
    if (item.element === "O" && item.charge > 0) allowed = 3;
    if (allowed !== undefined && bondLoad[atomIndex] > allowed + 0.05) {
      valenceIssues.push({
        atomIndex,
        element: item.element,
        observed: bondLoad[atomIndex],
        expected: allowed,
        sourceToken: item.sourceToken,
      });
    }
  });

  let extent = 2.8;
  atoms.forEach((item) => { extent = Math.max(extent, Math.hypot(item.x, item.y, item.z)); });
  return {
    model: {
      atoms,
      bonds,
      viewSize: Math.max(8.2, extent * 2.45),
      atomScale: atoms.length > 32 ? 0.58 : atoms.length > 18 ? 0.74 : 1,
      ringCount,
      stereoCount,
      valenceIssues,
    },
  };
}
