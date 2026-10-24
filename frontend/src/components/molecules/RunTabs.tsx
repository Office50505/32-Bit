export type RunTab = "validation" | "standardization" | "properties" | "evidence" | "provenance";

const TABS: { id: RunTab; label: string }[] = [
  { id: "validation", label: "Validation" },
  { id: "standardization", label: "Standardization" },
  { id: "properties", label: "Properties" },
  { id: "evidence", label: "Evidence" },
  { id: "provenance", label: "Provenance" },
];

export function RunTabs({ active, onChange }: { active: RunTab; onChange: (tab: RunTab) => void }) {
  return (
    <div className="run-tabs" role="tablist" aria-label="Run result sections">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
