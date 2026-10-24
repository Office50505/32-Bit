import { ProgressStep } from "../molecules/ProgressStep";

const STEPS = ["Source", "Confirm", "Validate", "Compare", "Report"] as const;

export function ProgressRail({ activeStep }: { activeStep: number }) {
  return (
    <aside className="progress-rail" aria-label="Analysis progress">
      <ol>
        {STEPS.map((label, index) => (
          <ProgressStep
            key={label}
            label={label}
            state={index < activeStep ? "complete" : index === activeStep ? "active" : "pending"}
            isLast={index === STEPS.length - 1}
          />
        ))}
      </ol>
    </aside>
  );
}
