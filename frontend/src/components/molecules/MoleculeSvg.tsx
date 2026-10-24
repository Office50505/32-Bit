interface MoleculeSvgProps {
  svg?: string | null;
  label: string;
  compact?: boolean;
}

export function MoleculeSvg({ svg, label, compact = false }: MoleculeSvgProps) {
  if (!svg) {
    return (
      <div className={`molecule-svg molecule-svg--empty ${compact ? "molecule-svg--compact" : ""}`}>
        Structure cannot be drawn safely
      </div>
    );
  }
  return (
    <div
      className={`molecule-svg ${compact ? "molecule-svg--compact" : ""}`}
      role="img"
      aria-label={label}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
