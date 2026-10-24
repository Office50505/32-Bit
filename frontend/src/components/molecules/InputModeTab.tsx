import type { LucideIcon } from "lucide-react";

export type InputMode = "paper" | "photo" | "draw" | "data";

interface InputModeTabProps {
  active: boolean;
  icon: LucideIcon;
  label: string;
  mode: InputMode;
  onSelect: (mode: InputMode) => void;
}

export function InputModeTab({ active, icon: Icon, label, mode, onSelect }: InputModeTabProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className={`input-mode ${active ? "input-mode--active" : ""}`}
      onClick={() => onSelect(mode)}
    >
      <Icon size={19} strokeWidth={1.75} aria-hidden="true" />
      <span>{label}</span>
    </button>
  );
}
