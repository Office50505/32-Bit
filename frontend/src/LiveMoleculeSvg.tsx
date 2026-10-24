export function LiveMoleculeSvg({ svg, zoom = 1 }: { svg?: string | null; zoom?: number }) {
  if (!svg) return <div className="live-svg">RDKit could not draw this structure safely. Review the diagnostic report.</div>;
  return <img className="live-depiction" style={{ transform: `scale(${zoom})` }} src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`} alt="RDKit molecular depiction" />;
}
