import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { API_BASE_URL, apiGet } from "../../shared/api";
import type { AnnouncementOut, AnnouncementsPageResponse, ListenerStatus } from "./types";
import "./announcements.css";

const PAGE_SIZE = 50;

export default function AnnouncementsPage() {
  const [exchange, setExchange] = useState("All");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [liveItems, setLiveItems] = useState<AnnouncementOut[]>([]);

  const query = useQuery({
    queryKey: ["announcements", exchange, search, offset],
    queryFn: () =>
      apiGet<AnnouncementsPageResponse>(
        `/announcements?limit=${PAGE_SIZE}&offset=${offset}` +
          (exchange !== "All" ? `&exchange=${encodeURIComponent(exchange)}` : "") +
          (search ? `&search=${encodeURIComponent(search)}` : "")
      ),
  });

  const status = useQuery({
    queryKey: ["announcements", "status"],
    queryFn: () => apiGet<ListenerStatus>("/announcements/status"),
    refetchInterval: 5000,
  });

  // Live push via SSE -- new rows appear here immediately rather than
  // waiting for the next poll (replaces the old Streamlit dashboard's
  // 3-second st.cache_data(ttl=3) polling hack).
  useEffect(() => {
    const es = new EventSource(`${API_BASE_URL}/announcements/stream`);
    es.onmessage = (ev) => {
      try {
        const item = JSON.parse(ev.data) as AnnouncementOut;
        setLiveItems((prev) => [item, ...prev].slice(0, 100));
      } catch {
        // keep-alive comment frames aren't JSON -- ignore
      }
    };
    return () => es.close();
  }, []);

  useEffect(() => {
    setLiveItems([]);
  }, [exchange, search]);

  const rows = useMemo(() => {
    const liveIds = new Set(liveItems.map((i) => i.id));
    const fetched = (query.data?.items ?? []).filter((i) => !liveIds.has(i.id));
    return offset === 0 ? [...liveItems, ...fetched] : fetched;
  }, [liveItems, query.data, offset]);

  return (
    <div className="page">
      <h1>Corporate Announcements</h1>

      {status.data?.auth_expired && (
        <div className="banner banner-error">
          TrueData session expired -- refresh TRUEDATA_AUTH_TOKEN in Trading_bot/.env and restart the backend.
        </div>
      )}
      {!status.data?.auth_expired && status.data?.last_error && (
        <div className="banner banner-warning">Listener warning: {status.data.last_error}</div>
      )}
      {status.data && (
        <p className="status-line">
          Listener: {status.data.running ? "running" : "stopped"}
          {status.data.last_poll_utc
            ? ` -- last poll ${new Date(status.data.last_poll_utc).toLocaleTimeString()}`
            : ""}
        </p>
      )}

      <div className="filters">
        <select
          value={exchange}
          onChange={(e) => {
            setExchange(e.target.value);
            setOffset(0);
          }}
        >
          <option value="All">All exchanges</option>
          <option value="BSE">BSE</option>
          <option value="BSE+NSE">BSE+NSE</option>
        </select>
        <input
          placeholder="Search company / title / message"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
        />
      </div>

      {query.isLoading && <p>Loading...</p>}
      {query.isError && <p className="banner banner-error">{(query.error as Error).message}</p>}

      <div className="table-scroll">
        <table className="ann-table">
          <thead>
            <tr>
              <th>Time (IST)</th>
              <th>Company</th>
              <th>Exchange</th>
              <th>Title</th>
              <th>Result?</th>
              <th>PDF</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.id} className={liveItems.some((l) => l.id === a.id) ? "row-live" : ""}>
                <td>{a.announcement_time_ist}</td>
                <td>{a.stock_name}</td>
                <td>{a.exchange}</td>
                <td title={a.message ?? ""}>{a.title}</td>
                <td>
                  {a.financial_result_flag === 1 ? "Yes" : a.financial_result_flag === 0 ? "No" : "-"}
                </td>
                <td>
                  {a.pdf_path ? (
                    "✓"
                  ) : a.pdf_url ? (
                    <a href={a.pdf_url} target="_blank" rel="noreferrer">
                      link
                    </a>
                  ) : (
                    "-"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="pager">
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          Newer
        </button>
        <span>
          {rows.length === 0 ? 0 : offset + 1}-{offset + rows.length} of {query.data?.total ?? "..."}
        </span>
        <button
          disabled={!query.data || offset + PAGE_SIZE >= query.data.total}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Older
        </button>
      </div>
    </div>
  );
}
