import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../../shared/api";
import type { PositionItem, PositionsResponse } from "./types";
import "./trading.css";

function PositionsTable({ items, emptyLabel }: { items: PositionItem[]; emptyLabel: string }) {
  return (
    <div className="table-scroll">
      <table className="activity-table">
        <thead>
          <tr>
            <th>Account</th>
            <th>Symbol</th>
            <th>Exchange</th>
            <th>Product</th>
            <th>Qty</th>
            <th>Avg Price</th>
            <th>Last Price</th>
            <th>P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p, i) => (
            <tr key={`${p.zerodha_id}-${p.tradingsymbol}-${p.product}-${i}`}>
              <td>{p.zerodha_id}</td>
              <td>{p.tradingsymbol}</td>
              <td>{p.exchange}</td>
              <td>{p.product}</td>
              <td>{p.quantity}</td>
              <td>{p.average_price.toFixed(2)}</td>
              <td>{p.last_price.toFixed(2)}</td>
              <td className={p.pnl > 0 ? "pnl-pos" : p.pnl < 0 ? "pnl-neg" : ""}>{p.pnl.toFixed(2)}</td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={8}>{emptyLabel}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/** Symbol-wise P&L across every account in the shared Kite session --
 * ported from Kite_API_31.py's get_open_position_count() (the function
 * behind the GUI's "Total Profit" column). Read-only: calls kite.positions()
 * through the same session Window 1 establishes, refreshes every 10s.
 *
 * Split into Open/Closed today (2026-08-17) -- everything used to render
 * in one flat table, open and already-flat (qty=0) positions mixed
 * together with no visual distinction. A trader asked "what's open right
 * now, at risk" as the first question this page should answer instantly,
 * not something to find by scanning a Qty column row by row. */
export default function PositionsPanel() {
  const positions = useQuery({
    queryKey: ["announcement-trading", "positions"],
    queryFn: () => apiGet<PositionsResponse>("/announcement-trading/positions"),
    refetchInterval: 10000,
  });

  const items = positions.data?.items ?? [];
  const totalPnl = positions.data?.total_pnl ?? 0;
  const open = items.filter((p) => p.quantity !== 0);
  const closed = items.filter((p) => p.quantity === 0);

  return (
    <div className="positions-panel">
      <div className="control-panel">
        <span
          className={totalPnl > 0 ? "pnl-total pnl-pos" : totalPnl < 0 ? "pnl-total pnl-neg" : "pnl-total"}
        >
          Total P&amp;L: {totalPnl.toFixed(2)}
        </span>
      </div>

      <h4>Open ({open.length})</h4>
      <PositionsTable items={open} emptyLabel="No open positions." />

      {closed.length > 0 && (
        <>
          <h4>Closed today ({closed.length})</h4>
          <PositionsTable items={closed} emptyLabel="" />
        </>
      )}
    </div>
  );
}
