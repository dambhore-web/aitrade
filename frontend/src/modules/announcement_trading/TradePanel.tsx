import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../shared/api";
import type { AnnouncementOut } from "../announcements/types";
import type {
  SessionStatus,
  TradeEntriesResponse,
  TradeEntry,
  TradeEntryCreate,
  TradingSettings,
} from "./types";
import "./trading.css";

export default function TradePanel({
  announcement,
  onClose,
}: {
  announcement: AnnouncementOut;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();

  const settings = useQuery({
    queryKey: ["announcement-trading", "settings"],
    queryFn: () => apiGet<TradingSettings>("/announcement-trading/settings"),
  });

  const sessionStatus = useQuery({
    queryKey: ["announcement-trading", "session-status"],
    queryFn: () => apiGet<SessionStatus>("/announcement-trading/session-status"),
  });
  const hasToken = !!sessionStatus.data?.connected;

  const entries = useQuery({
    queryKey: ["announcement-trading", "entries", announcement.id],
    queryFn: () =>
      apiGet<TradeEntriesResponse>(`/announcement-trading/entries?announcement_id=${announcement.id}`),
  });

  const [symbol, setSymbol] = useState(announcement.nse_symbol || announcement.stock_name || "");
  const [amount, setAmount] = useState<number>(settings.data?.amount ?? 0);
  const [notes, setNotes] = useState("");

  const saveEntry = useMutation({
    mutationFn: () =>
      apiPost<TradeEntry>("/announcement-trading/entries", {
        announcement_id: announcement.id,
        announcement_snapshot: `${announcement.stock_name ?? ""} - ${announcement.title ?? ""}`,
        symbol: symbol.trim().toUpperCase(),
        exchange: "NSE",
        amount,
        notes: notes || null,
      } satisfies TradeEntryCreate),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["announcement-trading", "entries", announcement.id] });
      setNotes("");
    },
  });

  const placeOrder = useMutation({
    mutationFn: (entryId: number) =>
      apiPost<TradeEntry>(`/announcement-trading/entries/${entryId}/place-order`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["announcement-trading", "entries", announcement.id] });
    },
  });

  return (
    <div className="trade-panel">
      <div className="trade-panel-header">
        <h3>Trade -- {announcement.stock_name}</h3>
        <button className="close-button" onClick={onClose}>
          ×
        </button>
      </div>
      <p className="trade-panel-message">{announcement.title}</p>

      {!hasToken && (
        <p className="banner banner-warning">
          No Kite token yet -- you can save trade parameters below, but placing an order needs a token
          first (run Kite_API_31.py's "Load User Data").
        </p>
      )}

      <div className="trade-form">
        <label>
          Symbol
          <input value={symbol} onChange={(e) => setSymbol(e.target.value)} />
        </label>
        <label>
          Amount (₹)
          <input type="number" value={amount} onChange={(e) => setAmount(Number(e.target.value))} />
        </label>
        <label className="notes-field">
          Notes
          <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="optional" />
        </label>
        <button onClick={() => saveEntry.mutate()} disabled={saveEntry.isPending || !symbol.trim()}>
          {saveEntry.isPending ? "Saving..." : "Save"}
        </button>
      </div>
      {saveEntry.isError && <p className="banner banner-error">{(saveEntry.error as Error).message}</p>}

      <h4>Entries for this announcement</h4>
      <table className="entries-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Notes</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {(entries.data?.entries ?? []).map((e) => (
            <tr key={e.id}>
              <td>{e.symbol}</td>
              <td>{e.amount ? `₹${e.amount.toLocaleString()}` : "-"}</td>
              <td className={`status-${e.status}`}>{e.status}</td>
              <td>{e.notes}</td>
              <td>
                {e.status === "draft" && (
                  <button
                    className="place-order-button"
                    disabled={placeOrder.isPending || !hasToken}
                    title={hasToken ? undefined : "No Kite session -- run \"Load User Data\" to get a token before trading"}
                    onClick={() => {
                      if (
                        window.confirm(
                          `Place a LIVE ${e.transaction_type} order for ${e.symbol}? This uses the connected Kite session and places a real order.`
                        )
                      ) {
                        placeOrder.mutate(e.id);
                      }
                    }}
                  >
                    Place order (LIVE)
                  </button>
                )}
              </td>
            </tr>
          ))}
          {entries.data?.entries.length === 0 && (
            <tr>
              <td colSpan={5}>No trade entries yet for this announcement.</td>
            </tr>
          )}
        </tbody>
      </table>
      {placeOrder.isError && <p className="banner banner-error">{(placeOrder.error as Error).message}</p>}
    </div>
  );
}
