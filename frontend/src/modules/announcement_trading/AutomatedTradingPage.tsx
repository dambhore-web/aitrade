import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { API_BASE_URL, apiGet, apiPost } from "../../shared/api";
import TradingSettingsPanel from "./TradingSettingsPanel";
import type { ActivityItem, ActivityResponse, AutoLoopStatus } from "./types";
import "./trading.css";

function ConnectionDot({ state, label }: { state: number | null | undefined; label: string }) {
  const color = state === 1 ? "#22c55e" : state === 0 ? "#ef4444" : "#999";
  return (
    <span className="conn-dot-wrap">
      <span className="conn-dot" style={{ background: color }} />
      {label}
    </span>
  );
}

export default function AutomatedTradingPage() {
  const queryClient = useQueryClient();
  const [liveItems, setLiveItems] = useState<ActivityItem[]>([]);

  const loopStatus = useQuery({
    queryKey: ["announcement-trading", "auto-status"],
    queryFn: () => apiGet<AutoLoopStatus>("/announcement-trading/auto/status"),
    refetchInterval: 3000,
  });

  const activity = useQuery({
    queryKey: ["announcement-trading", "activity"],
    queryFn: () => apiGet<ActivityResponse>("/announcement-trading/activity?limit=100"),
  });

  const start = useMutation({
    mutationFn: () => apiPost<AutoLoopStatus>("/announcement-trading/auto/start"),
    onSuccess: (data) => queryClient.setQueryData(["announcement-trading", "auto-status"], data),
  });

  const stop = useMutation({
    mutationFn: () => apiPost<AutoLoopStatus>("/announcement-trading/auto/stop"),
    onSuccess: (data) => queryClient.setQueryData(["announcement-trading", "auto-status"], data),
  });

  useEffect(() => {
    const es = new EventSource(`${API_BASE_URL}/announcement-trading/activity/stream`);
    es.onmessage = (ev) => {
      try {
        const item = JSON.parse(ev.data) as ActivityItem;
        setLiveItems((prev) => [item, ...prev].slice(0, 200));
      } catch {
        // keep-alive frame
      }
    };
    return () => es.close();
  }, []);

  const seenIds = new Set(liveItems.map((i) => i.id));
  const rows = [...liveItems, ...(activity.data?.items ?? []).filter((i) => !seenIds.has(i.id))];

  return (
    <div className="page">
      <h1>Announcement Auto-Trading</h1>
      <p className="status-line">
        Window 1 (below): create a Kite session and set trading parameters. Window 2: start the automatic
        scan-classify-trade loop and watch what it does, live.
      </p>

      <h2>Window 1 -- Session &amp; Settings</h2>
      <TradingSettingsPanel />

      <h2>Window 2 -- Live Trading</h2>
      <div className="control-panel">
        <button
          className="start-button"
          onClick={() => start.mutate()}
          disabled={start.isPending || loopStatus.data?.running}
        >
          START
        </button>
        <button
          className="stop-button"
          onClick={() => stop.mutate()}
          disabled={stop.isPending || !loopStatus.data?.running}
        >
          STOP
        </button>
        <ConnectionDot state={loopStatus.data?.state_bse} label="BSE" />
        <ConnectionDot state={loopStatus.data?.state_nse} label="NSE" />
        <span className="processed-count">{loopStatus.data?.processed_count ?? 0} processed</span>
        <span className={loopStatus.data?.running ? "loop-pill loop-running" : "loop-pill loop-stopped"}>
          {loopStatus.data?.running ? "running" : "stopped"}
        </span>
      </div>
      {start.isError && <p className="banner banner-error">{(start.error as Error).message}</p>}
      {loopStatus.data?.last_error && (
        <p className="banner banner-warning">{loopStatus.data.last_error}</p>
      )}

      <div className="table-scroll">
        <table className="activity-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th>Category</th>
              <th>Sentiment</th>
              <th>Outcome</th>
              <th>Text</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((item) => (
              <tr key={item.id} className={item.order_placed ? "row-ordered" : ""}>
                <td>{new Date(item.ts_utc).toLocaleTimeString()}</td>
                <td>{item.symbol}</td>
                <td>{item.category}</td>
                <td>{item.sentiment}</td>
                <td>
                  {item.order_placed ? (
                    <span className="outcome-ordered">ORDER PLACED (qty {item.quantity})</span>
                  ) : (
                    <span className="outcome-skipped">{item.skip_reason}</span>
                  )}
                </td>
                <td title={item.text_snippet ?? ""}>{item.text_snippet}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6}>No activity yet -- start the loop above.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
