import type { ReactNode } from "react";
import { ShieldCheck } from "lucide-react";

import { AppHeader } from "../organisms/AppHeader";
import { ProgressRail } from "../organisms/ProgressRail";

interface AppShellProps {
  activeStep: number;
  children: ReactNode;
}

export function AppShell({ activeStep, children }: AppShellProps) {
  return (
    <div className="app-shell">
      <AppHeader />
      <div className="app-shell__body">
        <ProgressRail activeStep={activeStep} />
        <main className="app-main">{children}</main>
      </div>
      <footer className="app-footer">
        <span><ShieldCheck size={18} /> Deterministic analysis · transformations and hashes are recorded.</span>
        <span>Research prototype · frozen reference snapshots are not configured</span>
      </footer>
    </div>
  );
}
