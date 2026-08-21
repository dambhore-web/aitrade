import { Link } from "react-router-dom";
import StatusBadge from "../../shared/StatusBadge";
import { useAnnouncementStatus, useEquityStatus } from "../../shared/useTradingStatus";
import "./dashboard.css";

/** New home page (Phase 1 of the navigation redesign) -- replaces the old
 * plain link list. Answers "what's live and what's it holding" without
 * opening a module, reading the same /status endpoints the modules
 * already use. See docs/requirements.md and the published UX proposal.
 * The risk strip itself now renders from the app shell (App.tsx), above
 * every page including this one -- not duplicated here. */
export default function DashboardPage() {
  const announcement = useAnnouncementStatus();
  const equity = useEquityStatus();

  return (
    <div className="page dashboard-page">
      <h1>Dashboard</h1>

      <div className="dashboard-cards">
        <Link to="/announcements" className="dashboard-card">
          <div className="card-top">
            <div>
              <div className="card-title">Announcement Trading</div>
              <div className="card-desc">Scans BSE/NSE announcements, classifies, trades automatically</div>
            </div>
            {!announcement.isLoading && <StatusBadge state={announcement.state} />}
          </div>
          <div className="card-metrics">
            <span>
              <b>{announcement.openPositions}</b>
              <br />
              open position{announcement.openPositions === 1 ? "" : "s"}
            </span>
            <span>
              <b>₹{announcement.totalPnl.toFixed(2)}</b>
              <br />
              P&amp;L today
            </span>
          </div>
          {announcement.lastError && <div className="card-error">{announcement.lastError}</div>}
        </Link>

        <Link to="/equity" className="dashboard-card">
          <div className="card-top">
            <div>
              <div className="card-title">Equity Trading</div>
              <div className="card-desc">Indicator-based candle strategy, auto short + trailing exit</div>
            </div>
            {!equity.isLoading && <StatusBadge state={equity.state} />}
          </div>
          <div className="card-metrics">
            <span>
              <b>{equity.openPositions}</b>
              <br />
              open position{equity.openPositions === 1 ? "" : "s"}
            </span>
            <span>
              <b>{equity.signalsToday}</b>
              <br />
              signals today
            </span>
            <span>
              <b>{equity.watchlistCount}</b>
              <br />
              symbols watched
            </span>
          </div>
          {equity.lastError && <div className="card-error">{equity.lastError}</div>}
        </Link>
      </div>

      <div className="tools-row-label">Tools — no live orders</div>
      <div className="dashboard-tools">
        <Link to="/historical" className="tool-chip">
          Historical Data Extractor
        </Link>
        <Link to="/news-extractor" className="tool-chip">
          News Extractor
        </Link>
        <Link to="/bonus-buyback" className="tool-chip">
          Bonus / Buyback Download
        </Link>
      </div>
    </div>
  );
}
