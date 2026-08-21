import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../shared/api";
import type { TradeEntriesResponse, TradeEntryCreate } from "./types";
import "./trading.css";

/** A "failed" entry's `order_result` carries the real reason (e.g. "Your
 * order could not be converted to a After Market Order (AMO)"), but
 * nothing in the UI ever showed it -- the table just said "failed", and
 * finding out why meant asking someone to go read backend logs. Extracts
 * the per-account error message(s) so they render right in the row. */
function orderErrors(orderResult: string | null): string | null {
  if (!orderResult) return null;
  try {
    const parsed = JSON.parse(orderResult) as { results?: Array<{ zerodha_id?: string; error?: string }> };
    const errors = (parsed.results ?? []).filter((r) => r.error);
    if (errors.length === 0) return null;
    return errors.map((r) => (r.zerodha_id ? `${r.zerodha_id}: ${r.error}` : r.error)).join("; ");
  } catch {
    return null;
  }
}

const EMPTY_FORM: TradeEntryCreate = {
  symbol: "",
  exchange: "NSE",
  transaction_type: "BUY",
  amount: undefined,
  quantity: undefined,
  stop_loss_pct: undefined,
  target_pct: undefined,
  order_type: undefined,
  product_type: undefined,
  variety: undefined,
  notes: "",
};

/** Manual per-symbol trade entry -- the form `docs/requirements.md` always
 * documented as part of Module B ("the manual per-announcement flow, still
 * available on the Announcements page") but that never actually got built
 * on the frontend, despite the backend endpoints (POST /entries, POST
 * /entries/{id}/place-order), types, and even the trade-panel/trade-form
 * CSS already existing and waiting for it. Added 2026-08-17.
 *
 * Two-step by design, matching the backend: creating an entry only saves a
 * draft (no order). Placing it is a separate, explicit action -- exactly
 * like the automatic loop's own gate, a human has to actually click Place
 * Order for anything to trade for real. Fields left blank on the entry
 * (order_type/product_type/stop_loss_pct/target_pct) fall back to whatever
 * Session & Settings has configured at place-order time -- the selects
 * below default to those same values so what's shown always matches what
 * would actually be used.
 *
 * Collapsed by default (same `.collapse-toggle`/`.settings-body` pattern
 * TradingSettingsPanel uses) -- a trader pointed out this got the same
 * permanently-expanded treatment as Positions on first ship, even though
 * it's an occasional override action, not something checked every visit.
 * Fixed 2026-08-17. */
export default function TradeEntryPanel() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const [form, setForm] = useState<TradeEntryCreate>(EMPTY_FORM);
  const [amountMode, setAmountMode] = useState<"amount" | "quantity">("amount");

  const entries = useQuery({
    queryKey: ["announcement-trading", "entries"],
    queryFn: () => apiGet<TradeEntriesResponse>("/announcement-trading/entries"),
    refetchInterval: 15000,
  });

  const create = useMutation({
    mutationFn: () => apiPost("/announcement-trading/entries", form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["announcement-trading", "entries"] });
      setForm(EMPTY_FORM);
    },
  });

  const placeOrder = useMutation({
    mutationFn: (entryId: number) => apiPost(`/announcement-trading/entries/${entryId}/place-order`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["announcement-trading", "entries"] }),
  });

  const set = <K extends keyof TradeEntryCreate>(key: K, value: TradeEntryCreate[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const entryList = entries.data?.entries ?? [];
  const draftCount = entryList.filter((e) => e.status === "draft").length;

  return (
    <div className="trading-settings">
      <button className="collapse-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "▾" : "▸"} New trade entry
        {draftCount > 0 && <span className="session-pill session-off">{draftCount} draft pending</span>}
      </button>
      {open && (
        <div className="settings-body trade-panel">
          <p className="trade-panel-message">
            Save a draft for any symbol, then place it yourself when ready -- this never fires an order on
            its own. Blank fields use whatever Session &amp; Settings has configured.
          </p>

          <form
        className="trade-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (!form.symbol.trim()) return;
          create.mutate();
        }}
      >
        <label>
          Symbol
          <input
            value={form.symbol}
            onChange={(e) => set("symbol", e.target.value.toUpperCase())}
            placeholder="e.g. INFY"
            required
          />
        </label>
        <label>
          Exchange
          <select value={form.exchange ?? "NSE"} onChange={(e) => set("exchange", e.target.value)}>
            <option value="NSE">NSE</option>
            <option value="BSE">BSE</option>
          </select>
        </label>
        <label>
          Transaction
          <select
            value={form.transaction_type ?? "BUY"}
            onChange={(e) => set("transaction_type", e.target.value)}
          >
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </label>

        <label>
          Size by
          <select
            value={amountMode}
            onChange={(e) => {
              const mode = e.target.value as "amount" | "quantity";
              setAmountMode(mode);
              if (mode === "amount") set("quantity", undefined);
              else set("amount", undefined);
            }}
          >
            <option value="amount">Amount (₹)</option>
            <option value="quantity">Quantity</option>
          </select>
        </label>
        {amountMode === "amount" ? (
          <label>
            Amount (₹)
            <input
              type="number"
              value={form.amount ?? ""}
              placeholder="uses Settings default"
              onChange={(e) => set("amount", e.target.value === "" ? undefined : Number(e.target.value))}
            />
          </label>
        ) : (
          <label>
            Quantity
            <input
              type="number"
              value={form.quantity ?? ""}
              onChange={(e) => set("quantity", e.target.value === "" ? undefined : Number(e.target.value))}
            />
          </label>
        )}

        <label>
          Order variety
          <select value={form.variety ?? ""} onChange={(e) => set("variety", e.target.value || undefined)}>
            <option value="">(Settings default)</option>
            <option value="regular">regular</option>
            <option value="co">co</option>
            <option value="bo">bo</option>
          </select>
        </label>
        <label>
          Order type
          <select value={form.order_type ?? ""} onChange={(e) => set("order_type", e.target.value || undefined)}>
            <option value="">(Settings default)</option>
            <option value="MARKET">MARKET</option>
            <option value="SL-M">SL-M</option>
            <option value="LIMIT">LIMIT</option>
          </select>
        </label>
        <label>
          Market/product type
          <select
            value={form.product_type ?? ""}
            onChange={(e) => set("product_type", e.target.value || undefined)}
          >
            <option value="">(Settings default)</option>
            <option value="MTF">MTF</option>
            <option value="MIS">MIS</option>
            <option value="CNC">CNC</option>
          </select>
        </label>

        <label>
          GTT stop loss (%)
          <input
            type="number"
            step="0.01"
            value={form.stop_loss_pct ?? ""}
            placeholder="uses Settings default"
            onChange={(e) => set("stop_loss_pct", e.target.value === "" ? undefined : Number(e.target.value))}
          />
        </label>
        <label>
          GTT target (%)
          <input
            type="number"
            step="0.01"
            value={form.target_pct ?? ""}
            placeholder="uses Settings default"
            onChange={(e) => set("target_pct", e.target.value === "" ? undefined : Number(e.target.value))}
          />
        </label>

        <label className="notes-field">
          Notes
          <input value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} />
        </label>

        <button type="submit" disabled={create.isPending || !form.symbol.trim()}>
          {create.isPending && <span className="spinner" aria-hidden="true" />}
          Save Draft
        </button>
      </form>
      {create.isError && <p className="banner banner-error">{(create.error as Error).message}</p>}
      {placeOrder.isError && <p className="banner banner-error">{(placeOrder.error as Error).message}</p>}

      <div className="table-scroll">
        <table className="entries-table">
          <thead>
            <tr>
              <th>Created</th>
              <th>Symbol</th>
              <th>Side</th>
              <th>Amount</th>
              <th>Qty</th>
              <th>Notes</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {entryList.map((entry) => (
              <tr key={entry.id}>
                <td>{new Date(entry.created_utc).toLocaleString()}</td>
                <td>{entry.symbol}</td>
                <td>{entry.transaction_type}</td>
                <td>{entry.amount ?? "--"}</td>
                <td>{entry.quantity ?? "--"}</td>
                <td>{entry.notes}</td>
                <td className={`status-${entry.status}`}>
                  {entry.status}
                  {entry.status === "failed" && orderErrors(entry.order_result) && (
                    <div className="entry-error">{orderErrors(entry.order_result)}</div>
                  )}
                </td>
                <td>
                  {entry.status === "draft" && (
                    <button
                      className="place-order-button"
                      disabled={placeOrder.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Place a REAL order for ${entry.symbol} (${entry.transaction_type})? This executes an actual trade through every connected Kite account.`
                          )
                        ) {
                          placeOrder.mutate(entry.id);
                        }
                      }}
                    >
                      {placeOrder.isPending && placeOrder.variables === entry.id && (
                        <span className="spinner" aria-hidden="true" />
                      )}
                      Place Order
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {entryList.length === 0 && (
              <tr>
                <td colSpan={8}>No trade entries yet.</td>
              </tr>
            )}
          </tbody>
        </table>
          </div>
        </div>
      )}
    </div>
  );
}
