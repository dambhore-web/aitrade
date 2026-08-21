import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../../shared/api";
import type { EquityPositionItem, EquityPositionsResponse } from "./types";
import "./equity.css";

function PositionsTable({ items, emptyLabel }: { items: EquityPositionItem[]; emptyLabel: string }) {
  return (
    <div className="table-scroll">
      <table className="signals-table">
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

/** Open short positions + live P&L for the equity auto-trading loop.
 * Split into Open/Closed today (2026-08-17), same reasoning as
 * announcement_trading/PositionsPanel.tsx -- "what's open right now" is
 * the first thing a trader wants answered instantly, not found by
 * scanning a Qty column. Since this endpoint only ever returns
 * quantity<0 (short) rows in the first place (see
 * equity_auto_trading/router.py's own filter), "closed" here means the
 * qty has ticked back to 0 since the last refresh, not a full trade
 * history -- there's no separate closed-positions endpoint yet. */
export default function EquityPositionsPanel() {
  const positions = useQuery({
    queryKey: ["equity-auto-trading", "positions"],
    queryFn: () => apiGet<EquityPositionsResponse>("/equity-auto-trading/positions"),
    refetchInterval: 10000,
  });

  const items = positions.data?.items ?? [];
  const totalPnl = positions.data?.total_pnl ?? 0;
  const open = items.filter((p) => p.quantity !== 0);
  const closed = items.filter((p) => p.quantity === 0);

  return (
    <div className="positions-panel">
      <div className="control-panel">
        <span className={totalPnl > 0 ? "pnl-total pnl-pos" : totalPnl < 0 ? "pnl-total pnl-neg" : "pnl-total"}>
          Total P&amp;L: {totalPnl.toFixed(2)}
        </span>
      </div>

      <h4>Open ({open.length})</h4>
      <PositionsTable items={open} emptyLabel="No open short positions." />

      {closed.length > 0 && (
        <>
          <h4>Closed today ({closed.length})</h4>
          <PositionsTable items={closed} emptyLabel="" />
        </>
      )}
    </div>
  );
}
