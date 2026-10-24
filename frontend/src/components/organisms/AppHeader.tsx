import { Search, UserRound } from "lucide-react";
import { NavLink } from "react-router-dom";

export function AppHeader() {
  return (
    <header className="app-header">
      <NavLink to="/" className="brand" aria-label="ProvenanceLab home">
        ProvenanceLab
      </NavLink>
      <nav className="app-nav" aria-label="Primary navigation">
        <NavLink to="/" end>New analysis</NavLink>
        <NavLink to="/runs/demo">Runs</NavLink>
        <a href="#about">About</a>
      </nav>
      <div className="app-header__tools">
        <button type="button" aria-label="Search runs"><Search size={21} /></button>
        <button type="button" aria-label="Account"><UserRound size={22} /></button>
      </div>
    </header>
  );
}
