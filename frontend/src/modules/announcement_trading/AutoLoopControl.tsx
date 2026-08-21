import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { API_BASE_URL, apiGet, apiPost } from "../../shared/api";
import StatusBadge from "../../shared/StatusBadge";
import type { ActivityItem, ActivityResponse, AutoLoopStatus } from "./types";
import "./trading.css";

/** One shared formatter for both the exchange's announcement time and our
 * own processed time, so the two columns are directly comparable instead of
 * showing up in different formats (one was "DD-Mon-YYYY HH:mm:ss" from NSE,
 * the other a bare 12-hour clock time with no date at all). Both render as
 * "DD-Mon-YYYY HH:mm:ss", 24-hour clock. */
function formatDateTime(value: string | null): string {
  if (!value) return "--";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const day = String(d.getDate()).padStart(2, "0");
  const month = d.toLocaleString("en-US", { month: "short" });
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${day}-${month}-${d.getFullYear()} ${hh}:${mm}:${ss}`;
}

/** Missing/unparseable an_dt sorts as "oldest possible" (-Infinity) rather
 * than epoch-0 or NaN, so those rows consistently sink to the bottom of a
 * descending sort instead of landing wherever a `new Date(null)` (which is
 * epoch 1970, not invalid) or a NaN comparison happens to put them. */
function anDtValue(value: string | null): number {
  if (!value) return -Infinity;
  const t = new Date(value).getTime();
  return Number.isNaN(t) ? -Infinity : t;
}

/** Same local calendar day as right now, in whatever timezone the browser
 * itself is in -- this desk runs in IST, so that's effectively an IST
 * calendar-day check without hardcoding an offset. */
function isToday(value: string | null): boolean {
  if (!value) return false;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
}

/** Prefers the announcement's own date; falls back to when we processed it
 * for the rare row where an_dt is missing/unparseable -- matches how the
 * table already treats an_dt as best-effort elsewhere (anDtValue above). */
function isRowToday(item: ActivityItem): boolean {
  return item.an_dt ? isToday(item.an_dt) : isToday(item.ts_utc);
}

function ConnectionDot({
  state,
  label,
  error,
}: {
  state: number | null | undefined;
  label: string;
  error?: string | null;
}) {
  const color = state === 1 ? "var(--live)" : state === 0 ? "var(--danger)" : "var(--stopped)";
  return (
    <span className="conn-dot-wrap" title={error ?? undefined}>
      <span className="conn-dot" style={{ background: color }} />
      {label}
    </span>
  );
}

/** The run/live-trading control -- START/STOP for the automatic
 * scan-classify-trade loop (Kite_API_31.py parity), connection status, and
 * a live feed of every announcement it looks at. Shown on both the
 * Announcements page (where you're already looking at the news) and its
 * own dedicated /auto-trading page. */
export default function AutoLoopControl() {
  const queryClient = useQueryClient();
  const [liveItems, setLiveItems] = useState<ActivityItem[]>([]);
  const [sentimentFilter, setSentimentFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<"all" | "NSE" | "BSE" | "TRUEWEALTH_BSE">("all");
  // Defaults on -- this feed is a live trading-desk view, and stale rows
  // from prior days (still returned by a broad "Fetch" pull) buried what
  // happened today underneath them. One click turns it off to look back.
  const [todayOnly, setTodayOnly] = useState(true);
  // Defaults to "orders" rather than "all" -- a trader watching this feed
  // to see what the bot actually DID was scrolling past 90+ routine
  // symbol_not_tradeable/neutral rows to find the 1-2 that mattered.
  // "All" is still one click away.
  const [outcomeFilter, setOutcomeFilter] = useState<"orders" | "skipped" | "all">("orders");
  // How many rows to fetch -- defaults to 100 (cheap, covers a normal
  // day), but "I can see only 100 news, I want to see everything" is a
  // real ask once the log has hundreds of rows. "All" sends a limit high
  // enough that it's never actually the binding constraint (activity_log
  // has run into the low thousands on a busy day, not more).
  const [rowLimit, setRowLimit] = useState<"100" | "500" | "all">("100");
  const limitParam = rowLimit === "all" ? 100000 : Number(rowLimit);

  const loopStatus = useQuery({
    queryKey: ["announcement-trading", "auto-status"],
    queryFn: () => apiGet<AutoLoopStatus>("/announcement-trading/auto/status"),
    refetchInterval: 3000,
  });

  // Fetches order_placed=true specifically when that's the active filter,
  // rather than fetching the general "most recent 100 rows of everything"
  // and filtering client-side -- on a busy day the handful of real orders
  // scroll out of that window long before 100 more rows have been
  // scanned since the last one (confirmed live 2026-08-17: 2 orders
  // placed among 912 total activity rows -- "Orders placed" showed
  // nothing even though orders really had been placed that day).
  const activity = useQuery({
    queryKey: ["announcement-trading", "activity", outcomeFilter, limitParam],
    queryFn: () =>
      apiGet<ActivityResponse>(
        outcomeFilter === "orders"
          ? `/announcement-trading/activity?limit=${limitParam}&order_placed=true`
          : `/announcement-trading/activity?limit=${limitParam}`
      ),
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
  const allRows = [...liveItems, ...(activity.data?.items ?? []).filter((i) => !seenIds.has(i.id))];
  const todayFiltered = todayOnly ? allRows.filter(isRowToday) : allRows;
  const outcomeFiltered =
    outcomeFilter === "all"
      ? todayFiltered
      : todayFiltered.filter((i) => (outcomeFilter === "orders" ? i.order_placed : i.skipped));
  const sourceFiltered =
    sourceFilter === "all" ? outcomeFiltered : outcomeFiltered.filter((i) => i.source === sourceFilter);
  const sentimentFiltered =
    sentimentFilter === "all" ? sourceFiltered : sourceFiltered.filter((i) => i.sentiment === sentimentFilter);
  // Rows were only ever in processing order (SSE arrival / id DESC), never
  // actually sorted by the announcement's own timestamp -- close most of
  // the time, but not guaranteed, and visibly wrong whenever hours_back
  // pulls in an older announcement after newer ones already processed.
  // Explicit sort by an_dt descending so "latest at the top" is always
  // true regardless of processing order; rows with no usable an_dt (blank/
  // unparseable) sink to the bottom rather than scattering through the list.
  const rows = [...sentimentFiltered].sort((a, b) => anDtValue(b.an_dt) - anDtValue(a.an_dt));

  // Independent of `activity` above -- that query's result set changes
  // shape with outcomeFilter, so counting order_placed rows out of
  // *that* would under-report whenever "orders" isn't the active filter.
  // This always asks the backend directly, so the badge is accurate
  // regardless of which filter is currently selected.
  const ordersPlacedTotal = useQuery({
    queryKey: ["announcement-trading", "activity", "orders-count"],
    queryFn: () => apiGet<ActivityResponse>("/announcement-trading/activity?limit=100&order_placed=true"),
    refetchInterval: 15000,
  });
  const ordersPlacedCount = ordersPlacedTotal.data?.items.length ?? 0;

  return (
    <div className="auto-loop-control">
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
        <ConnectionDot state={loopStatus.data?.state_bse} label="BSE" error={loopStatus.data?.bse_error} />
        <ConnectionDot state={loopStatus.data?.state_nse} label="NSE" error={loopStatus.data?.nse_error} />
        <span className="processed-count">{loopStatus.data?.processed_count ?? 0} processed</span>
        <StatusBadge state={loopStatus.data?.running ? "live" : "stopped"} />
      </div>
      {start.isError && <p className="banner banner-error">{(start.error as Error).message}</p>}
      {loopStatus.data?.last_error && (
        <p className="banner banner-warning">{loopStatus.data.last_error}</p>
      )}
      {loopStatus.data?.state_bse === 0 && (
        <p className="banner banner-warning">BSE: {loopStatus.data.bse_error}</p>
      )}
      {loopStatus.data?.state_nse === 0 && (
        <p className="banner banner-warning">NSE: {loopStatus.data.nse_error}</p>
      )}
      <p className="log-hint">
        Full logs: <code>aitrade\backend\logs\app.log</code> (also printed live in the terminal running
        uvicorn).
      </p>

      <div className="filter-row">
        <label className="checkbox-label today-only-toggle">
          <input type="checkbox" checked={todayOnly} onChange={(e) => setTodayOnly(e.target.checked)} />
          Today only
        </label>
        <label htmlFor="outcome-filter">Show</label>
        <select
          id="outcome-filter"
          value={outcomeFilter}
          onChange={(e) => setOutcomeFilter(e.target.value as "orders" | "skipped" | "all")}
        >
          <option value="orders">Orders placed ({ordersPlacedCount})</option>
          <option value="skipped">Skipped</option>
          <option value="all">All ({todayFiltered.length})</option>
        </select>
        <label htmlFor="row-limit">Fetch</label>
        <select id="row-limit" value={rowLimit} onChange={(e) => setRowLimit(e.target.value as "100" | "500" | "all")}>
          <option value="100">Last 100</option>
          <option value="500">Last 500</option>
          <option value="all">Everything</option>
        </select>
        <label htmlFor="source-filter">Source</label>
        <select
          id="source-filter"
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value as "all" | "NSE" | "BSE" | "TRUEWEALTH_BSE")}
        >
          <option value="all">All ({outcomeFiltered.length})</option>
          <option value="NSE">NSE ({outcomeFiltered.filter((i) => i.source === "NSE").length})</option>
          <option value="BSE">BSE ({outcomeFiltered.filter((i) => i.source === "BSE").length})</option>
          <option value="TRUEWEALTH_BSE">
            TrueWealth ({outcomeFiltered.filter((i) => i.source === "TRUEWEALTH_BSE").length})
          </option>
        </select>
        <label htmlFor="sentiment-filter">Sentiment</label>
        <select
          id="sentiment-filter"
          value={sentimentFilter}
          onChange={(e) => setSentimentFilter(e.target.value)}
        >
          <option value="all">All ({sourceFiltered.length})</option>
          {Array.from(new Set(sourceFiltered.map((i) => i.sentiment).filter((s): s is string => !!s))).map((s) => (
            <option key={s} value={s}>
              {s} ({sourceFiltered.filter((i) => i.sentiment === s).length})
            </option>
          ))}
        </select>
      </div>

      <div className="table-scroll">
        <table className="activity-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Announced</th>
              <th>Processed</th>
              <th>Symbol</th>
              <th>Category</th>
              <th>Sentiment</th>
              <th>Outcome</th>
              <th>Text</th>
              <th>Attachment</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((item) => (
              <tr key={item.id} className={item.order_placed ? "row-ordered" : ""}>
                <td>
                  {item.source && (
                    <span
                      className={
                        "source-pill " +
                        (item.source === "NSE"
                          ? "source-nse"
                          : item.source === "TRUEWEALTH_BSE"
                            ? "source-truewealth"
                            : "source-bse")
                      }
                    >
                      {item.source}
                    </span>
                  )}
                </td>
                <td>{formatDateTime(item.an_dt)}</td>
                <td>{formatDateTime(item.ts_utc)}</td>
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
                <td>
                  {item.attachment_url && (
                    <a href={item.attachment_url} target="_blank" rel="noopener noreferrer">
                      View
                    </a>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={9}>
                  {allRows.length === 0
                    ? "No activity yet -- click START above."
                    : outcomeFiltered.length === 0
                      ? outcomeFilter === "orders"
                        ? "No orders placed yet -- switch \"Show\" to All to see everything scanned."
                        : "No skipped items."
                      : `No ${sentimentFilter} items.`}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
