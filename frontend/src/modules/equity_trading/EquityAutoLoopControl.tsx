import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../shared/api";
import StatusBadge from "../../shared/StatusBadge";
import type { EquityAutoLoopStatus, EquityAutoSignalsResponse } from "./types";
import "./equity.css";

/** START/STOP control for the real equity scan+execute loop (ported from
 * new_trade_tool/scanner.py) -- runs independently of the Announcement
 * Trading auto-loop, its own thread/start/stop, but authenticates through
 * the SAME Kite session (Announcement Trading page's "Generate Token"
 * flow) instead of a second separate login. `mode` reflects
 * new_trade_tool/config.py's PAPER_TRADING flag as-is -- currently False
 * there, so LIVE means real orders via execution.place_trade_live() the
 * moment this is started, exactly like running scanner.py by hand would. */
export default function EquityAutoLoopControl() {
  const queryClient = useQueryClient();

  const status = useQuery({
    queryKey: ["equity-auto-trading", "status"],
    queryFn: () => apiGet<EquityAutoLoopStatus>("/equity-auto-trading/status"),
    refetchInterval: 3000,
  });

  const signals = useQuery({
    queryKey: ["equity-auto-trading", "signals"],
    queryFn: () => apiGet<EquityAutoSignalsResponse>("/equity-auto-trading/signals?limit=50"),
    refetchInterval: status.data?.running ? 5000 : false,
  });

  const start = useMutation({
    mutationFn: () => apiPost<EquityAutoLoopStatus>("/equity-auto-trading/start"),
    onSuccess: (data) => queryClient.setQueryData(["equity-auto-trading", "status"], data),
  });

  const stop = useMutation({
    mutationFn: () => apiPost<EquityAutoLoopStatus>("/equity-auto-trading/stop"),
    onSuccess: (data) => queryClient.setQueryData(["equity-auto-trading", "status"], data),
  });

  const mode = status.data?.mode;

  return (
    <div className="equity-auto-loop-control">
      <div className="control-panel">
        <button
          className="start-button"
          onClick={() => start.mutate()}
          disabled={start.isPending || status.data?.running}
        >
          START
        </button>
        <button
          className="stop-button"
          onClick={() => stop.mutate()}
          disabled={stop.isPending || !status.data?.running}
        >
          STOP
        </button>
        {mode && (
          <StatusBadge
            state={mode === "LIVE" ? "live" : "paper"}
            label={mode === "LIVE" ? "LIVE — real orders" : "PAPER — simulated"}
          />
        )}
        <span className="processed-count">{status.data?.open_positions ?? 0} open short positions</span>
        <span className="processed-count">{status.data?.watchlist_count ?? 0} symbols watched</span>
        <StatusBadge state={status.data?.running ? "live" : "stopped"} />
      </div>
      {start.isError && <p className="banner banner-error">{(start.error as Error).message}</p>}
      {status.data?.last_error && <p className="banner banner-warning">{status.data.last_error}</p>}

      <div className="table-scroll">
        <table className="signals-table">
          <thead>
            <tr>
              <th>Time (IST)</th>
              <th>Symbol</th>
              <th>Signal</th>
              <th>Price</th>
              <th>Meta</th>
            </tr>
          </thead>
          <tbody>
            {(signals.data?.items ?? []).map((s) => (
              <tr key={s.id}>
                <td>{s.dt_ist}</td>
                <td>{s.symbol}</td>
                <td className={`sig-${s.signal.toLowerCase()}`}>{s.signal}</td>
                <td>{s.close}</td>
                <td>{s.meta}</td>
              </tr>
            ))}
            {(signals.data?.items ?? []).length === 0 && (
              <tr>
                <td colSpan={5}>No signals yet -- click START above.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
