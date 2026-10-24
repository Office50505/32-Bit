import type { ReactNode } from "react";

import { StatusMark, type StatusTone } from "./StatusMark";

export function StatusLabel({
  tone,
  children,
}: {
  tone: StatusTone;
  children: ReactNode;
}) {
  const text = typeof children === "string" ? children : "Status";
  return (
    <span className={`status-label status-label--${tone}`}>
      <StatusMark tone={tone} label={text} />
      <span>{children}</span>
    </span>
  );
}
