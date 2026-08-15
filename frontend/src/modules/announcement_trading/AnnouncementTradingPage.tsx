import AutoLoopControl from "./AutoLoopControl";
import TradingSettingsPanel from "./TradingSettingsPanel";
import "./trading.css";

/** Corporate announcement trading -- scans BSE/NSE directly and trades off
 * what it finds. TrueData was dropped as a separate data source (not
 * needed -- this covers corporate announcements end to end on its own). */
export default function AnnouncementTradingPage() {
  return (
    <div className="page">
      <h1>Corporate Announcement Trading</h1>
      <p className="status-line">
        Window 1 (below): create a Kite session and set trading parameters. Window 2: start the automatic
        scan-classify-trade loop and watch what it does, live.
      </p>

      <h2>Window 1 -- Session &amp; Settings</h2>
      <TradingSettingsPanel />

      <h2>Window 2 -- Live Trading</h2>
      <AutoLoopControl />
    </div>
  );
}
