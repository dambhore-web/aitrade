import { NavLink } from "react-router-dom";
import StatusBadge from "./StatusBadge";
import { useAnnouncementStatus, useEquityStatus } from "./useTradingStatus";
import "./sidebar.css";

/** Left sidebar nav -- Phase 1 of the navigation redesign (see
 * docs/requirements.md and the published UX proposal). Groups pages into
 * Trading (live-order-placing modules, shown with a live status dot) and
 * Tools (data/research utilities, no live orders). Routes are unchanged
 * from the previous topbar -- this only changes the shell, not any
 * existing page's internals. */
export default function Sidebar() {
  const announcement = useAnnouncementStatus();
  const equity = useEquityStatus();

  return (
    <nav className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-mark">AI</span>
        aitrade
      </div>

      <div className="nav-group">
        <div className="nav-group-label">Trading</div>
        <NavLink to="/" end className="nav-item">
          Dashboard
        </NavLink>
        <NavLink to="/announcements" className="nav-item">
          <span className="nav-item-left">
            <span className={`nav-dot ${announcement.state}`} />
            Announcement Trading
          </span>
          {!announcement.isLoading && <StatusBadge state={announcement.state} />}
        </NavLink>
        <NavLink to="/equity" className="nav-item">
          <span className="nav-item-left">
            <span className={`nav-dot ${equity.state}`} />
            Equity Trading
          </span>
          {!equity.isLoading && <StatusBadge state={equity.state} />}
        </NavLink>
      </div>

      <div className="nav-group">
        <div className="nav-group-label">Tools</div>
        <NavLink to="/historical" className="nav-item">
          Historical Data
        </NavLink>
        <NavLink to="/news-extractor" className="nav-item">
          News Extractor
        </NavLink>
        <NavLink to="/bonus-buyback" className="nav-item">
          Bonus / Buyback
        </NavLink>
        <NavLink to="/screener" className="nav-item">
          Volatility Screener
        </NavLink>
        <NavLink to="/backtest" className="nav-item">
          Backtest
        </NavLink>
      </div>
    </nav>
  );
}
