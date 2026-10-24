import type { PropertyObservation } from "../../schemas/analysis";

export function PropertyValue({ observation }: { observation: PropertyObservation }) {
  if (observation.value === null) {
    return (
      <span className="property-value property-value--missing" title={observation.reason ?? undefined}>
        — <small>{observation.reason_code?.replaceAll("_", " ").toLowerCase()}</small>
      </span>
    );
  }
  return (
    <span className="property-value">
      {observation.value}
      {observation.unit ? <small>{observation.unit}</small> : null}
    </span>
  );
}
