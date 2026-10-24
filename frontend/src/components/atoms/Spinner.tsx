export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="spinner" role="status" aria-label={label}>
      <span className="spinner__ring" aria-hidden="true" />
    </span>
  );
}
