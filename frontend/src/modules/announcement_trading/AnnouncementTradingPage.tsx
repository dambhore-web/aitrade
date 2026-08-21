import AutoLoopControl from "./AutoLoopControl";
import PositionsPanel from "./PositionsPanel";
import SessionPanel from "./SessionPanel";
import TradeEntryPanel from "./TradeEntryPanel";
import TradingSettingsPanel from "./TradingSettingsPanel";
import TrueWealthControl from "./TrueWealthControl";
import Section from "../../shared/Section";
import "./trading.css";

/** Corporate announcement trading -- scans BSE/NSE directly and trades off
 * what it finds. TrueData was dropped as a separate data source (not
 * needed -- this covers corporate announcements end to end on its own).
 *
 * Every section renders inside Section (shared/Section.tsx) -- a bordered/
 * shadowed card with a distinct header band -- so sections read as clear,
 * separate blocks instead of a wall of content divided only by headings
 * (2026-08-17, after a trader called the page out for looking "merged").
 * TradeEntryPanel/TradingSettingsPanel manage their own collapse instead
 * of going through Section (they need a live badge in the header), but
 * use the identical card CSS so the look matches regardless.
 *
 * Section order is status-first (Phase 2 of the nav/UI redesign, see
 * docs/requirements.md), with Kite Session leading everything else
 * (2026-08-17): a session is the one prerequisite every other section on
 * this page needs, and unlike Settings it isn't configure-once -- Kite
 * tokens expire daily. Manual Trade Entry follows Positions, collapsed by
 * default since it's an occasional override action. Settings -- configured
 * once, revisited rarely -- moves last and stays collapsed too. The
 * "Window 1" / "Window 2" labels were leftovers from the legacy
 * PySimpleGUI desktop app's two-window layout -- dropped in favor of
 * naming each section by what it does. */
export default function AnnouncementTradingPage() {
  return (
    <div className="page">
      <h1>Announcement Trading</h1>
      <p className="status-line">Scans BSE/NSE announcements, classifies them, and trades automatically.</p>

      <Section title="Kite Session">
        <SessionPanel />
      </Section>

      <Section title="Status & Control">
        <AutoLoopControl />
      </Section>

      <Section title="TrueWealth Source (BSE, second poller)">
        <TrueWealthControl />
      </Section>

      <Section title="Positions & P&L">
        <PositionsPanel />
      </Section>

      <TradeEntryPanel />

      <TradingSettingsPanel />
    </div>
  );
}
