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
    </header>
  );
}
