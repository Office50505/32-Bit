interface ProgressStepProps {
  label: string;
  state: "complete" | "active" | "pending";
  isLast?: boolean;
}

export function ProgressStep({ label, state, isLast = false }: ProgressStepProps) {
  return (
    <li className={`progress-step progress-step--${state}`} aria-current={state === "active" ? "step" : undefined}>
      <span className="progress-step__marker" aria-hidden="true" />
      <span className="progress-step__label">{label}</span>
      {!isLast ? <span className="progress-step__line" aria-hidden="true" /> : null}
    </li>
  );
}
