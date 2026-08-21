import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../shared/api";
import Section from "../../shared/Section";
import { usePersistedJobId } from "../../shared/usePersistedJobId";
import type {
  BacktestJobCreateRequest,
  BacktestJobCreateResponse,
  BacktestJobStatusResponse,
  TradeRow,
} from "./types";
import "./backtest.css";

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}
function daysAgoIso(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export default function BacktestPage() {
  const queryClient = useQueryClient();

  const [customSymbols, setCustomSymbols] = useState("");
  const [useDateRange, setUseDateRange] = useState(true);
  const [startDate, setStartDate] = useState(daysAgoIso(30));
  const [endDate, setEndDate] = useState(todayIso());
  const [strategy, setStrategy] = useState<"wisestock" | "breakout">("wisestock");
  const [jobId, setJobId] = usePersistedJobId("backtest");

  const createJob = useMutation({
    mutationFn: () => {
      const symbols = customSymbols
        .split(/[,\n\r\t ]+/)
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);
      return apiPost<BacktestJobCreateResponse>("/backtest/jobs", {
        symbols: symbols.length > 0 ? symbols : null,
        start_date: useDateRange ? startDate : null,
        end_date: useDateRange ? endDate : null,
        strategy,
      } satisfies BacktestJobCreateRequest);
    },
    onSuccess: (res) => setJobId(res.id),
  });

  const jobStatus = useQuery({
    queryKey: ["backtest", "job", jobId],
    queryFn: () => apiGet<BacktestJobStatusResponse>(`/backtest/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2000 : false),
    retry: false,
  });

  useEffect(() => {
    if (jobStatus.isError && jobId) {
      setJobId(null);
    }
  }, [jobStatus.isError, jobId, setJobId]);

  const cancelJob = useMutation({
    mutationFn: () => apiPost<BacktestJobStatusResponse>(`/backtest/jobs/${jobId}/cancel`),
    onSuccess: (data) => queryClient.setQueryData(["backtest", "job", jobId], data),
  });

  const job = jobStatus.data;
  const running = createJob.isPending || job?.status === "running";

  return (
    <div className="page">
      <h1>Backtest</h1>

      <Section title="Backtest Settings">
        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            createJob.mutate();
          }}
        >
          <label>
            Strategy
            <select value={strategy} onChange={(e) => setStrategy(e.target.value as "wisestock" | "breakout")}>
              <option value="wisestock">WiseStockTrader (VWAP crossover)</option>
              <option value="breakout">Breakout (Opening-Range)</option>
            </select>
          </label>

          <label className="field-wide">
            Symbols (optional -- leave blank to replay every symbol with candle history)
            <textarea
              rows={2}
              placeholder="Leave blank for ALL symbols, or list specific ones: RELIANCE, TCS, SUZLON..."
              value={customSymbols}
              onChange={(e) => setCustomSymbols(e.target.value)}
            />
          </label>

          <label className="checkbox-label">
            <input type="checkbox" checked={useDateRange} onChange={(e) => setUseDateRange(e.target.checked)} />
            Limit to a date range
          </label>
          {useDateRange && (
            <>
              <label>
                Start date
                <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </label>
              <label>
                End date
                <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </label>
            </>
          )}
          {!useDateRange && (
            <p className="field-hint field-wide">
              Replays every available day per symbol -- can take a while across many symbols. A date range
              (above) is usually faster and enough to judge recent behavior.
            </p>
          )}

          <div className="field-wide">
            <button className="primary-button" type="submit" disabled={running}>
              {running && <span className="spinner" />}
              {running ? "Replaying..." : "Run Backtest"}
            </button>
          </div>
          {createJob.isError && <p className="banner banner-error field-wide">{(createJob.error as Error).message}</p>}
        </form>
      </Section>

      {job && (
        <Section
          title="Replay Progress"
          headerRight={
            <div style={{ display: "flex", alignItems: "center", gap: "0.9rem" }}>
              <span className="section-status">
                {job.status === "running" ? "replaying" : job.status} -- {job.done_count}/{job.total_count} symbols
              </span>
              {job.status === "running" && (
                <button className="secondary-button" onClick={() => cancelJob.mutate()} disabled={cancelJob.isPending}>
                  {cancelJob.isPending && <span className="spinner" />}
                  {cancelJob.isPending ? "Cancelling..." : "Cancel"}
                </button>
              )}
            </div>
          }
        >
          <div className="progress-track">
            <div
              className={`progress-fill ${job.status === "running" ? "indeterminate" : ""}`}
              style={{ width: job.status === "done" ? "100%" : job.status === "running" ? undefined : "0%" }}
            />
          </div>
          {job.status === "cancelled" && (
            <p className="banner banner-warning">Cancelled -- results below reflect only the symbols replayed before stopping.</p>
          )}
          {job.error && <p className="banner banner-error">{job.error}</p>}
          <div className="log-panel">
            {job.log_tail.map((line, i) => (
              <div key={i}>{line}</div>
            ))}
          </div>
        </Section>
      )}

      {job && job.summary.trades > 0 && (
        <Section title="Summary">
          <div className="bt-summary-grid">
            <div className="bt-stat">
              <div className="bt-stat-num">{job.summary.trades}</div>
              <div className="bt-stat-lbl">Trades</div>
            </div>
            <div className="bt-stat">
              <div className="bt-stat-num">{job.summary.win_rate.toFixed(1)}%</div>
              <div className="bt-stat-lbl">Win Rate</div>
            </div>
            <div className={`bt-stat ${job.summary.total_pnl >= 0 ? "bt-stat-pos" : "bt-stat-neg"}`}>
              <div className="bt-stat-num">₹{job.summary.total_pnl.toLocaleString("en-IN")}</div>
              <div className="bt-stat-lbl">Total P&amp;L</div>
            </div>
            <div className="bt-stat">
              <div className="bt-stat-num">₹{job.summary.avg_pnl.toLocaleString("en-IN")}</div>
              <div className="bt-stat-lbl">Avg P&amp;L / Trade</div>
            </div>
            <div className="bt-stat bt-stat-pos">
              <div className="bt-stat-num">₹{job.summary.max_win.toLocaleString("en-IN")}</div>
              <div className="bt-stat-lbl">Max Win</div>
            </div>
            <div className="bt-stat bt-stat-neg">
              <div className="bt-stat-num">₹{job.summary.max_loss.toLocaleString("en-IN")}</div>
              <div className="bt-stat-lbl">Max Loss</div>
            </div>
          </div>
        </Section>
      )}

      <Section title={`Trades (${job?.trades.length ?? 0})`}>
        <div className="table-scroll">
          <table className="entries-table bt-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Date</th>
                <th>Price</th>
                <th>Ex. Date</th>
                <th>Ex. Price</th>
                <th>Exit Reason</th>
                <th>% chg</th>
                <th>Profit</th>
                <th>% Profit</th>
                <th>Cum. Profit</th>
                <th># bars</th>
                <th>MAE</th>
                <th>MFE</th>
              </tr>
            </thead>
            <tbody>
              {(job?.trades ?? []).map((t: TradeRow, i) => (
                <tr key={i}>
                  <td className="bt-symbol">{t.Symbol}</td>
                  <td>{t.Date}</td>
                  <td>{t.Price.toFixed(2)}</td>
                  <td>{t["Ex. date"]}</td>
                  <td>{t["Ex. Price"].toFixed(2)}</td>
                  <td>{t["Exit reason"]}</td>
                  <td className={t["% chg"] >= 0 ? "bt-pos" : "bt-neg"}>{t["% chg"].toFixed(2)}</td>
                  <td className={t.Profit >= 0 ? "bt-pos" : "bt-neg"}>{t.Profit.toFixed(2)}</td>
                  <td className={t["% Profit"] >= 0 ? "bt-pos" : "bt-neg"}>{t["% Profit"].toFixed(2)}</td>
                  <td className={t["Cum. Profit"] >= 0 ? "bt-pos" : "bt-neg"}>{t["Cum. Profit"].toFixed(2)}</td>
                  <td>{t["# bars"]}</td>
                  <td>{t.MAE !== null ? t.MAE.toFixed(2) : "--"}</td>
                  <td>{t.MFE !== null ? t.MFE.toFixed(2) : "--"}</td>
                </tr>
              ))}
              {(!job || job.trades.length === 0) && (
                <tr>
                  <td colSpan={13} style={{ textAlign: "center", color: "var(--ink-soft)" }}>
                    {!job
                      ? "Run a backtest above to see trades here."
                      : job.status === "done"
                        ? "No completed SELL -> COVER trades in this range."
                        : "Waiting for trades..."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}
