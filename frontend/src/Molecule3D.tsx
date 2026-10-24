import { useEffect, useMemo, useRef } from "react";

import {
  ELEMENT_STYLES,
  FALLBACK_ELEMENT_STYLE,
  parseSmilesSketch,
  type MoleculeSketch,
  type SketchAtom,
} from "./moleculeSketch";

interface Props {
  smiles: string;
  label: string;
  autorotate: boolean;
  showLabels: boolean;
  highlightedAtoms?: number[];
  resetSignal: number;
  zoom: number;
  compact?: boolean;
}

interface ProjectedPoint {
  x: number;
  y: number;
  z: number;
  scale: number;
}

interface ViewState {
  yaw: number;
  pitch: number;
  wheelZoom: number;
  dragging: boolean;
  previousX: number;
  previousY: number;
}

const DEFAULT_VIEW: ViewState = {
  yaw: -0.24,
  pitch: 0.53,
  wheelZoom: 1,
  dragging: false,
  previousX: 0,
  previousY: 0,
};

function project(
  atom: SketchAtom,
  width: number,
  height: number,
  model: MoleculeSketch,
  view: ViewState,
  zoom: number,
): ProjectedPoint {
  const cosYaw = Math.cos(view.yaw);
  const sinYaw = Math.sin(view.yaw);
  const cosPitch = Math.cos(view.pitch);
  const sinPitch = Math.sin(view.pitch);
  const x = atom.x * cosYaw - atom.z * sinYaw;
  const rotatedZ = atom.x * sinYaw + atom.z * cosYaw;
  const y = atom.y * cosPitch - rotatedZ * sinPitch;
  const z = atom.y * sinPitch + rotatedZ * cosPitch;
  const fit = Math.min(width, height) / model.viewSize;
  const perspective = 6.4 / (6.4 + z * 0.24);
  const scale = zoom * view.wheelZoom;
  return {
    x: width / 2 + x * fit * scale * perspective,
    y: height / 2 - y * fit * scale * perspective,
    z,
    scale: perspective,
  };
}

function drawBackground(context: CanvasRenderingContext2D, width: number, height: number) {
  const glow = context.createRadialGradient(
    width / 2,
    height / 2,
    20,
    width / 2,
    height / 2,
    Math.min(width, height) * 0.55,
  );
  glow.addColorStop(0, "rgba(0, 127, 131, 0.075)");
  glow.addColorStop(0.55, "rgba(0, 127, 131, 0.018)");
  glow.addColorStop(1, "rgba(255, 255, 255, 0)");
  context.fillStyle = glow;
  context.fillRect(0, 0, width, height);

  context.fillStyle = "rgba(88, 125, 132, 0.14)";
  for (let y = 16; y < height; y += 32) {
    for (let x = 16; x < width; x += 32) context.fillRect(x, y, 1, 1);
  }
}

function drawBond(
  context: CanvasRenderingContext2D,
  start: ProjectedPoint,
  end: ProjectedPoint,
  order: number,
  highlighted: boolean,
  atomScale: number,
) {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = Math.hypot(dx, dy) || 1;
  const offsetX = (-dy / length) * 3.5;
  const offsetY = (dx / length) * 3.5;
  const lineOffsets = order >= 2.75 ? [-1.45, 0, 1.45] : order >= 1.75 ? [-1, 1] : [0];

  lineOffsets.forEach((direction) => {
    const x1 = start.x + offsetX * direction;
    const y1 = start.y + offsetY * direction;
    const x2 = end.x + offsetX * direction;
    const y2 = end.y + offsetY * direction;
    const gradient = context.createLinearGradient(x1, y1, x2, y2);
    if (highlighted) {
      gradient.addColorStop(0, "rgba(207, 32, 47, 0.65)");
      gradient.addColorStop(0.5, "rgba(232, 66, 81, 0.96)");
      gradient.addColorStop(1, "rgba(207, 32, 47, 0.65)");
    } else {
      gradient.addColorStop(0, "rgba(69, 96, 106, 0.58)");
      gradient.addColorStop(0.5, "rgba(31, 61, 70, 0.9)");
      gradient.addColorStop(1, "rgba(69, 96, 106, 0.58)");
    }
    context.beginPath();
    context.moveTo(x1, y1);
    context.lineTo(x2, y2);
    context.lineWidth = (highlighted ? 5.5 : 4.2) * Math.max(0.68, atomScale);
    context.strokeStyle = gradient;
    context.shadowColor = highlighted ? "rgba(207, 32, 47, 0.38)" : "rgba(0, 127, 131, 0.12)";
    context.shadowBlur = highlighted ? 12 : 4;
    context.stroke();
    context.shadowBlur = 0;
  });
}

function drawAtom(
  context: CanvasRenderingContext2D,
  atom: SketchAtom,
  point: ProjectedPoint,
  highlighted: boolean,
  atomScale: number,
  zoom: number,
  showLabel: boolean,
  time: number,
) {
  const style = ELEMENT_STYLES[atom.element] ?? FALLBACK_ELEMENT_STYLE;
  const radius = Math.max(4.5, style.radius * point.scale * zoom * atomScale);
  if (highlighted) {
    const pulse = 1 + Math.sin(time * 0.006) * 0.08;
    context.beginPath();
    context.arc(point.x, point.y, radius * 1.7 * pulse, 0, Math.PI * 2);
    context.strokeStyle = "rgba(207, 32, 47, 0.68)";
    context.lineWidth = 1.5;
    context.shadowColor = "rgba(207, 32, 47, 0.45)";
    context.shadowBlur = 14;
    context.stroke();
    context.shadowBlur = 0;
  }

  const gradient = context.createRadialGradient(
    point.x - radius * 0.34,
    point.y - radius * 0.38,
    radius * 0.05,
    point.x,
    point.y,
    radius,
  );
  gradient.addColorStop(0, "#ffffff");
  gradient.addColorStop(0.2, style.edge);
  gradient.addColorStop(0.6, style.color);
  gradient.addColorStop(1, style.shade);
  context.beginPath();
  context.arc(point.x, point.y, radius, 0, Math.PI * 2);
  context.fillStyle = gradient;
  context.shadowColor = highlighted ? "rgba(207, 32, 47, 0.42)" : "rgba(11, 45, 51, 0.2)";
  context.shadowBlur = highlighted ? 16 : 9;
  context.fill();
  context.shadowBlur = 0;
  context.strokeStyle = highlighted ? "rgba(207, 32, 47, 0.9)" : "rgba(255, 255, 255, 0.78)";
  context.lineWidth = 0.9;
  context.stroke();

  if (showLabel) {
    context.fillStyle = atom.element === "H" ? "#23353c" : "#ffffff";
    context.font = `800 ${Math.max(8, radius * 0.65)}px Inter, system-ui, sans-serif`;
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.shadowColor = "rgba(0, 0, 0, 0.35)";
    context.shadowBlur = 3;
    context.fillText(atom.element, point.x, point.y + 0.4);
    context.shadowBlur = 0;
  }
}

export default function Molecule3D({
  smiles,
  label,
  autorotate,
  showLabels,
  highlightedAtoms = [],
  resetSignal,
  zoom,
  compact = false,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const viewRef = useRef<ViewState>({ ...DEFAULT_VIEW });
  const renderPropsRef = useRef({ autorotate, showLabels, highlightedAtoms, zoom });
  renderPropsRef.current = { autorotate, showLabels, highlightedAtoms, zoom };
  const result = useMemo(() => parseSmilesSketch(smiles), [smiles]);

  useEffect(() => {
    viewRef.current = { ...DEFAULT_VIEW };
  }, [resetSignal, smiles]);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    const model = result.model;
    if (!host || !canvas || !model) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    let animationFrame = 0;
    let lastTime = performance.now();
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const resizeObserver = new ResizeObserver(() => {
      const bounds = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, Math.round(bounds.width * ratio));
      const height = Math.max(1, Math.round(bounds.height * ratio));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
    });
    resizeObserver.observe(host);

    const onPointerDown = (event: PointerEvent) => {
      const view = viewRef.current;
      view.dragging = true;
      view.previousX = event.clientX;
      view.previousY = event.clientY;
      canvas.setPointerCapture(event.pointerId);
      host.dataset.interacted = "true";
    };
    const onPointerMove = (event: PointerEvent) => {
      const view = viewRef.current;
      if (!view.dragging) return;
      view.yaw += (event.clientX - view.previousX) * 0.009;
      view.pitch = Math.max(-1.4, Math.min(1.4, view.pitch + (event.clientY - view.previousY) * 0.009));
      view.previousX = event.clientX;
      view.previousY = event.clientY;
    };
    const endDrag = (event: PointerEvent) => {
      viewRef.current.dragging = false;
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    };
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const view = viewRef.current;
      view.wheelZoom = Math.max(0.6, Math.min(1.7, view.wheelZoom - event.deltaY * 0.001));
      host.dataset.interacted = "true";
    };
    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);
    canvas.addEventListener("wheel", onWheel, { passive: false });

    const render = (time: number) => {
      const bounds = canvas.getBoundingClientRect();
      const width = bounds.width;
      const height = bounds.height;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      if (canvas.width !== Math.max(1, Math.round(width * ratio)) || canvas.height !== Math.max(1, Math.round(height * ratio))) {
        canvas.width = Math.max(1, Math.round(width * ratio));
        canvas.height = Math.max(1, Math.round(height * ratio));
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      drawBackground(context, width, height);

      const view = viewRef.current;
      const props = renderPropsRef.current;
      const delta = Math.min(40, time - lastTime);
      lastTime = time;
      if (props.autorotate && !reduceMotion && !view.dragging) view.yaw += delta * 0.00016;
      const totalZoom = props.zoom * view.wheelZoom;
      const points = model.atoms.map((item) => project(item, width, height, model, view, props.zoom));
      const highlighted = new Set([
        ...model.valenceIssues.map((issue) => issue.atomIndex),
        ...props.highlightedAtoms,
      ]);
      const renderables: Array<
        | { type: "bond"; z: number; index: number }
        | { type: "atom"; z: number; index: number }
      > = [];
      model.bonds.forEach((item, index) => {
        renderables.push({ type: "bond", z: (points[item.a].z + points[item.b].z) / 2, index });
      });
      model.atoms.forEach((_, index) => renderables.push({ type: "atom", z: points[index].z, index }));
      renderables.sort((first, second) => first.z - second.z);

      renderables.forEach((entry) => {
        if (entry.type === "bond") {
          const item = model.bonds[entry.index];
          drawBond(
            context,
            points[item.a],
            points[item.b],
            item.order,
            highlighted.has(item.a) || highlighted.has(item.b),
            model.atomScale,
          );
          return;
        }
        const atom = model.atoms[entry.index];
        const isHighlighted = highlighted.has(entry.index);
        drawAtom(
          context,
          atom,
          points[entry.index],
          isHighlighted,
          model.atomScale,
          totalZoom,
          props.showLabels || atom.element !== "C" || isHighlighted,
          time,
        );
      });

      if (!compact && width > 520 && model.valenceIssues.length) {
        model.valenceIssues.forEach((issue) => {
          const point = points[issue.atomIndex];
          const text = `${issue.element}${issue.atomIndex + 1} · ${issue.observed} bonds / expected ${issue.expected}`;
          context.font = "800 10px Inter, system-ui, sans-serif";
          const labelWidth = Math.max(150, context.measureText(text).width + 22);
          const labelX = point.x + labelWidth + 28 < width ? point.x + 20 : point.x - labelWidth - 20;
          const labelY = Math.max(12, Math.min(height - 34, point.y - 34));
          context.beginPath();
          context.moveTo(point.x, point.y);
          context.lineTo(labelX < point.x ? labelX + labelWidth : labelX, labelY + 14);
          context.strokeStyle = "rgba(207, 32, 47, 0.7)";
          context.lineWidth = 1;
          context.stroke();
          context.fillStyle = "rgba(255, 255, 255, 0.96)";
          context.fillRect(labelX, labelY, labelWidth, 28);
          context.strokeStyle = "rgba(207, 32, 47, 0.78)";
          context.strokeRect(labelX, labelY, labelWidth, 28);
          context.fillStyle = "#b7192d";
          context.textAlign = "left";
          context.textBaseline = "middle";
          context.fillText(text, labelX + 11, labelY + 14.5);
        });
      }
      animationFrame = requestAnimationFrame(render);
    };
    animationFrame = requestAnimationFrame(render);
    return () => {
      cancelAnimationFrame(animationFrame);
      resizeObserver.disconnect();
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", endDrag);
      canvas.removeEventListener("pointercancel", endDrag);
      canvas.removeEventListener("wheel", onWheel);
    };
  }, [compact, result.model]);

  if (result.error) {
    return (
      <div className={`molecule-3d molecule-3d--fallback ${compact ? "molecule-3d--compact" : ""}`} role="img" aria-label={`${label} could not be rendered in 3D`}>
        <strong>3D sketch unavailable</strong>
        <span>{result.error}</span>
      </div>
    );
  }

  return (
    <div ref={hostRef} className={`molecule-3d ${compact ? "molecule-3d--compact" : ""}`}>
      <canvas ref={canvasRef} aria-label={`Interactive 3D SMILES sketch for ${label}`} />
      {!compact ? <span className="molecule-3d__hint">Drag to rotate · scroll to zoom</span> : null}
    </div>
  );
}
