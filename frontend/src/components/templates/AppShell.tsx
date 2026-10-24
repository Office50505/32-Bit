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
        <span><ShieldCheck size={18} /> No source leaves your run record. Every transformation is logged.</span>
        <nav aria-label="Legal"><a href="#privacy">Privacy</a><a href="#terms">Terms</a><a href="#help">Help</a></nav>
      </footer>
    </div>
  );
}
