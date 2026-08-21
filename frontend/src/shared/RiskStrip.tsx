import StatusBadge from "./StatusBadge";
import { useAnnouncementStatus, useEquityStatus } from "./useTradingStatus";

/** Persistent risk strip -- originally only shown on the Dashboard, but a
 * trader reading this page said it best: "I lose the top-level risk view
 * the moment I scroll ... once I'm here reading the activity feed, 'is
 * this thing actually live and what's it holding' is out of view unless I
 * scroll back to the very top." Moved into the app shell (App.tsx, above
 * every routed page) so it's always visible regardless of which page or
 * how far down it you've scrolled. Added 2026-08-17. */
export default function RiskStrip() {
  const announcement = useAnnouncementStatus();
  const equity = useEquityStatus();

  const loopsRunning = (announcement.running ? 1 : 0) + (equity.running ? 1 : 0);
  const openPositions = announcement.openPositions + equity.openPositions;
  const errors = [announcement.lastError, equity.lastError].filter(Boolean).length;
  const anyLive = loopsRunning > 0;

  return (
    <div className={`risk-strip ${anyLive ? "risk-strip-live" : ""}`}>
      <div className="risk-metric">
        <span className="num">{loopsRunning}</span>
        <span className="lbl">loop{loopsRunning === 1 ? "" : "s"} running</span>
      </div>
      <div className="risk-metric">
        <span className="num">{openPositions}</span>
        <span className="lbl">open position{openPositions === 1 ? "" : "s"}</span>
      </div>
      <div className="risk-metric">
        <span className="num">₹{announcement.totalPnl.toFixed(2)}</span>
        <span className="lbl">announcement P&amp;L today</span>
      </div>
      <div className="risk-metric">
        <span className={`num ${errors > 0 ? "num-danger" : ""}`}>{errors}</span>
        <span className="lbl">error{errors === 1 ? "" : "s"}</span>
      </div>
      {anyLive ? (
        <StatusBadge state="live" label="LIVE TRADING ACTIVE" />
      ) : (
        <StatusBadge state="stopped" label="NOTHING RUNNING" />
      )}
    </div>
  );
}
