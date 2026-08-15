import AutoLoopControl from "./AutoLoopControl";
import TradingSettingsPanel from "./TradingSettingsPanel";
import "./trading.css";

/** Standalone view of the same run control shown inline on the
 * Announcements page -- useful for keeping an eye on the loop without the
 * announcements table alongside it. */
export default function AutomatedTradingPage() {
  return (
    <div className="page">
      <h1>Announcement Auto-Trading</h1>
      <p className="status-line">
        Window 1 (below): create a Kite session and set trading parameters. Window 2: start the automatic
        scan-classify-trade loop and watch what it does, live. Same controls also appear on the
        Announcements page.
      </p>

      <h2>Window 1 -- Session &amp; Settings</h2>
      <TradingSettingsPanel />

      <h2>Window 2 -- Live Trading</h2>
      <AutoLoopControl />
    </div>
  );
}
