export function LiveMoleculeSvg({ svg }: { svg?: string | null }) {
  if (!svg) return <div className="live-svg">RDKit could not draw this structure safely. Review the diagnostic report.</div>;
  return <img className="live-depiction" src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`} alt="RDKit molecular depiction" />;
}
