import { Code2 } from "lucide-react";
import { NavLink } from "react-router-dom";

export function AppHeader() {
  return (
    <header className="app-header">
      <NavLink to="/" className="brand" aria-label="ProvenanceLab home">
        ProvenanceLab
      </NavLink>
      <nav className="app-nav" aria-label="Primary navigation">
        <NavLink to="/" end>New analysis</NavLink>
      </nav>
      <a
        className="source-link"
        href="https://github.com/Office50505/32-Bit"
        target="_blank"
        rel="noreferrer"
      >
        <Code2 size={18} aria-hidden="true" />
        <span>Source</span>
      </a>
    </header>
  );
}
