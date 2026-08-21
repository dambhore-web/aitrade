import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost } from "../../shared/api";
import type { EquityWatchlistResponse } from "./types";
import "./equity.css";

/** Add/remove symbols traded by the equity auto-trading loop --
 * new_trade_tool/watchlist.csv, previously only editable by hand in that
 * file. Read once at loop start, NOT live-reloaded like Trade Settings'
 * amount/strategy -- an edit here takes effect the next time the loop is
 * (re)started, not on the very next signal. */
export default function WatchlistEditor() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("");
  const [addText, setAddText] = useState("");

  const watchlist = useQuery({
    queryKey: ["equity-auto-trading", "watchlist"],
    queryFn: () => apiGet<EquityWatchlistResponse>("/equity-auto-trading/watchlist"),
  });

  const addSymbols = useMutation({
    mutationFn: (symbols: string[]) => apiPost<EquityWatchlistResponse>("/equity-auto-trading/watchlist", { symbols }),
    onSuccess: (data) => {
      queryClient.setQueryData(["equity-auto-trading", "watchlist"], data);
      setAddText("");
    },
  });

  const removeSymbol = useMutation({
    mutationFn: (symbol: string) => apiDelete<EquityWatchlistResponse>(`/equity-auto-trading/watchlist/${symbol}`),
    onSuccess: (data) => {
      queryClient.setQueryData(["equity-auto-trading", "watchlist"], data);
    },
  });

  const symbols = watchlist.data?.symbols ?? [];
  const visible = filter.trim()
    ? symbols.filter((s) => s.includes(filter.trim().toUpperCase()))
    : symbols;

  const handleAdd = () => {
    const parsed = addText
      .split(/[,\n\r\t ]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (parsed.length > 0) addSymbols.mutate(parsed);
  };

  return (
    <div className="watchlist-editor">
      <p className="field-hint">
        {symbols.length} symbols currently traded. Adding or removing here writes new_trade_tool/watchlist.csv
        directly -- the change takes effect the next time the equity auto-trading loop is stopped and started
        again, not immediately.
      </p>

      <div className="watchlist-add-row">
        <textarea
          rows={2}
          placeholder="Add symbols -- paste a list (comma, space, or newline separated): RELIANCE, TCS, SUZLON..."
          value={addText}
          onChange={(e) => setAddText(e.target.value)}
        />
        <button className="save-button" onClick={handleAdd} disabled={addSymbols.isPending || !addText.trim()}>
          {addSymbols.isPending && <span className="spinner" aria-hidden="true" />}
          {addSymbols.isPending ? "Adding..." : "ADD"}
        </button>
      </div>
      {addSymbols.isError && <p className="banner banner-error">{(addSymbols.error as Error).message}</p>}

      <input
        className="watchlist-filter"
        type="text"
        placeholder="Filter symbols..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />

      {removeSymbol.isError && <p className="banner banner-error">{(removeSymbol.error as Error).message}</p>}

      <div className="watchlist-grid">
        {visible.map((s) => (
          <span key={s} className="watchlist-chip">
            {s}
            <button
              type="button"
              className="watchlist-chip-remove"
              title={`Remove ${s}`}
              onClick={() => removeSymbol.mutate(s)}
              disabled={removeSymbol.isPending}
            >
              ×
            </button>
          </span>
        ))}
        {watchlist.isLoading && <p>Loading watchlist...</p>}
        {!watchlist.isLoading && visible.length === 0 && <p>No symbols match "{filter}".</p>}
      </div>
    </div>
  );
}
