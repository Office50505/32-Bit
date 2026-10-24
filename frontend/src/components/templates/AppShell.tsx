import type { ReactNode } from "react";

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
    </div>
  );
}
