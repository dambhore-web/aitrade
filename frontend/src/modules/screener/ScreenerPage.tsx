import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../shared/api";
import Section from "../../shared/Section";
import { usePersistedJobId } from "../../shared/usePersistedJobId";
import type { AuthStatus, ScreenerJobCreateRequest, ScreenerJobCreateResponse, ScreenerJobStatusResponse, ScreenerRow } from "./types";
import "./screener.css";

function formatCr(v: number) {
  return v.toLocaleString("en-IN", { maximumFractionDigits: 1 });
}
function formatVolume(v: number) {
  if (v >= 1e7) return `${(v / 1e7).toFixed(2)}Cr`;
  if (v >= 1e5) return `${(v / 1e5).toFixed(2)}L`;
  return v.toLocaleString("en-IN");
}

export default function ScreenerPage() {
  const queryClient = useQueryClient();

  const authStatus = useQuery({
    queryKey: ["screener", "auth-status"],
    queryFn: () => apiGet<AuthStatus>("/screener/auth/status"),
    refetchInterval: 10000,
  });

  const [lookbackDays, setLookbackDays] = useState(30);
  const [atrPeriod, setAtrPeriod] = useState(14);
  const [minPrice, setMinPrice] = useState(50);
  const [minTurnoverCr, setMinTurnoverCr] = useState(5);
  const [minAtrPct, setMinAtrPct] = useState(1.5);
  const [maxAtrPct, setMaxAtrPct] = useState(8);
  const [eqSeriesOnly, setEqSeriesOnly] = useState(true);
  const [maxSymbols, setMaxSymbols] = useState(500);
  const [customSymbols, setCustomSymbols] = useState("");
  const [showOnlyPassing, setShowOnlyPassing] = useState(true);
  const [elderScreen, setElderScreen] = useState(false);
  // "PASS" in the Filter column is only Level 1 (volatility/liquidity) --
  // easy to mistake for "the answer" when Level 2 is also on, since most
  // Level-1 passes still show no real Elder signal (that's the point --
  // divergence setups are meant to be rare, not "most days, most stocks").
  // Defaults to showing only actual Elder setups whenever Level 2 ran, so
  // the table answers "which stocks do I take" directly instead of
  // requiring a scan through a column for "✓ SHORT SETUP".
  const [elderOnly, setElderOnly] = useState(true);

  const [jobId, setJobId] = usePersistedJobId("screener");

  const createJob = useMutation({
    mutationFn: () => {
      const symbols = customSymbols
        .split(/[,\n\r\t ]+/)
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);
      return apiPost<ScreenerJobCreateResponse>("/screener/jobs", {
        exchange: "NSE",
        lookback_days: lookbackDays,
        atr_period: atrPeriod,
        min_price: minPrice,
        min_avg_turnover_cr: minTurnoverCr,
        min_atr_pct: minAtrPct,
        max_atr_pct: maxAtrPct,
        eq_series_only: eqSeriesOnly,
        max_symbols: symbols.length > 0 ? null : maxSymbols,
        symbols: symbols.length > 0 ? symbols : null,
        elder_screen: elderScreen,
      } satisfies ScreenerJobCreateRequest);
    },
    onSuccess: (res) => setJobId(res.id),
  });

  const jobStatus = useQuery({
    queryKey: ["screener", "job", jobId],
    queryFn: () => apiGet<ScreenerJobStatusResponse>(`/screener/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1500 : false),
    retry: false,
  });

  useEffect(() => {
    if (jobStatus.isError && jobId) {
      setJobId(null);
    }
  }, [jobStatus.isError, jobId, setJobId]);

  const cancelJob = useMutation({
    mutationFn: () => apiPost<ScreenerJobStatusResponse>(`/screener/jobs/${jobId}/cancel`),
    onSuccess: (data) => queryClient.setQueryData(["screener", "job", jobId], data),
  });

  const job = jobStatus.data;
  const running = createJob.isPending || job?.status === "running";
  const rows = job?.rows ?? [];
  const passingCount = rows.filter((r) => r.passes_filters).length;
  const elderPassedCount = rows.filter((r) => r.elder_passed).length;
  const shownRows = rows
    .filter((r) => (showOnlyPassing ? r.passes_filters : true))
    .filter((r) => (job?.elder_screen && elderOnly ? r.elder_passed : true));

  if (authStatus.isLoading) return <div className="page">Checking Kite session...</div>;

  if (!authStatus.data?.authenticated) {
    return (
      <div className="page">
        <h1>Volatility Screener</h1>
        <div className="banner banner-error">
          No Kite session -- generate a token first on the Announcement Trading page, then come back here.
          This tool uses that same shared session.
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Volatility Screener</h1>

      <Section title="Scan Settings">
        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            createJob.mutate();
          }}
        >
          <label>
            Lookback (trading days)
            <input type="number" min={15} max={180} value={lookbackDays} onChange={(e) => setLookbackDays(Number(e.target.value))} />
          </label>
          <label>
            ATR period
            <input type="number" min={5} max={30} value={atrPeriod} onChange={(e) => setAtrPeriod(Number(e.target.value))} />
          </label>
          <label>
            Min price (₹)
            <input type="number" min={0} value={minPrice} onChange={(e) => setMinPrice(Number(e.target.value))} />
          </label>
          <label>
            Min avg turnover (₹ cr)
            <input type="number" min={0} step="0.5" value={minTurnoverCr} onChange={(e) => setMinTurnoverCr(Number(e.target.value))} />
          </label>
          <label>
            Min ATR%
            <input type="number" min={0} step="0.1" value={minAtrPct} onChange={(e) => setMinAtrPct(Number(e.target.value))} />
          </label>
          <label>
            Max ATR%
            <input type="number" min={0} step="0.1" value={maxAtrPct} onChange={(e) => setMaxAtrPct(Number(e.target.value))} />
          </label>
          <label>
            Universe cap
            <input
              type="number"
              min={1}
              max={3000}
              value={maxSymbols}
              onChange={(e) => setMaxSymbols(Number(e.target.value))}
              disabled={customSymbols.trim().length > 0}
            />
            <span className="field-hint">Ignored if you list explicit symbols below.</span>
          </label>
          <label className="checkbox-label">
            <input type="checkbox" checked={eqSeriesOnly} onChange={(e) => setEqSeriesOnly(e.target.checked)} />
            EQ series only (excludes BE/BZ restricted series via NSE's own listing)
          </label>
          <label className="checkbox-label">
            <input type="checkbox" checked={elderScreen} onChange={(e) => setElderScreen(e.target.checked)} />
            Level 2: Elder Triple Screen (weekly tide + daily divergence)
          </label>
          {elderScreen && (
            <p className="field-hint field-wide" style={{ marginTop: "-0.5rem" }}>
              Runs only against symbols that pass Level 1 above -- needs ~1 year of history per
              candidate, so it adds real time to the scan proportional to how many pass.
            </p>
          )}

          <label className="field-wide">
            Explicit symbols (optional -- overrides the universe cap/EQ filter above)
            <textarea
              rows={2}
              placeholder="Leave blank to scan the broad universe, or list specific symbols: RELIANCE, TCS, INFY..."
              value={customSymbols}
              onChange={(e) => setCustomSymbols(e.target.value)}
            />
          </label>

          <div className="field-wide">
            <button className="primary-button" type="submit" disabled={running}>
              {running && <span className="spinner" />}
              {running ? "Scanning..." : "Run Scan"}
            </button>
          </div>
          {createJob.isError && <p className="banner banner-error field-wide">{(createJob.error as Error).message}</p>}
        </form>
      </Section>

      {job && (
        <Section
          title="Scan Progress"
          headerRight={
            <div style={{ display: "flex", alignItems: "center", gap: "0.9rem" }}>
              <span className="section-status">
                {job.status === "running" ? "scanning" : job.status} -- {job.done_count}/{job.total_count}
                {job.elder_screen && job.elder_total_count > 0 && (
                  <> · Elder {job.elder_done_count}/{job.elder_total_count}</>
                )}
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
            <p className="banner banner-warning">Cancelled -- results below reflect only the symbols scanned before stopping.</p>
          )}
          {job.error && <p className="banner banner-error">{job.error}</p>}
          <div className="log-panel">
            {job.log_tail.map((line, i) => (
              <div key={i}>{line}</div>
            ))}
          </div>
        </Section>
      )}

      <Section
        title={
          job?.elder_screen
            ? `Results (${elderPassedCount} Elder setup${elderPassedCount === 1 ? "" : "s"} / ${passingCount} pass Level 1 / ${rows.length} scanned)`
            : `Results (${passingCount} pass / ${rows.length} scanned)`
        }
        headerRight={
          <div style={{ display: "flex", gap: "1rem" }}>
            {job?.elder_screen && (
              <label className="checkbox-label" style={{ fontSize: "0.82rem", color: "var(--ink-soft)" }}>
                <input type="checkbox" checked={elderOnly} onChange={(e) => setElderOnly(e.target.checked)} />
                Elder setups only
              </label>
            )}
            <label className="checkbox-label" style={{ fontSize: "0.82rem", color: "var(--ink-soft)" }}>
              <input type="checkbox" checked={showOnlyPassing} onChange={(e) => setShowOnlyPassing(e.target.checked)} />
              Show passing only
            </label>
          </div>
        }
      >
        <div className="table-scroll">
          <table className="entries-table scr-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Last Close</th>
                <th>ATR%</th>
                <th>Hist Vol%</th>
                <th>Avg Turnover (₹cr)</th>
                <th>Avg Volume</th>
                <th>Avg Gap%</th>
                <th>Score</th>
                <th>Filter</th>
                {job?.elder_screen && (
                  <>
                    <th>Weekly Tide</th>
                    <th>Divergence</th>
                    <th>Elder</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {shownRows.map((r: ScreenerRow) => (
                <tr key={r.symbol} className={r.elder_passed ? "scr-row-elder" : r.passes_filters ? "scr-row-pass" : ""}>
                  <td className="scr-symbol">{r.symbol}</td>
                  <td>{r.last_close.toFixed(2)}</td>
                  <td>{r.atr_pct.toFixed(2)}</td>
                  <td>{r.hist_vol_pct.toFixed(1)}</td>
                  <td>{formatCr(r.avg_turnover_cr)}</td>
                  <td>{formatVolume(r.avg_volume)}</td>
                  <td>{r.avg_gap_pct.toFixed(2)}</td>
                  <td className="scr-score">{r.passes_filters ? r.score.toFixed(1) : "--"}</td>
                  <td>
                    {r.passes_filters ? (
                      <span className="scr-pass">PASS</span>
                    ) : (
                      <span className="scr-fail">FAIL</span>
                    )}
                  </td>
                  {job?.elder_screen && (
                    <>
                      <td>
                        {r.weekly_trend_down === null ? (
                          "--"
                        ) : r.weekly_trend_down ? (
                          <span className="scr-tide-down">↓ Down</span>
                        ) : (
                          <span className="scr-tide-up">↑ Up</span>
                        )}
                      </td>
                      <td>
                        {r.divergence_class ? (
                          <span className="scr-divergence">
                            Class {r.divergence_class}
                            {r.bull_power_shrink_pct !== null && ` (-${r.bull_power_shrink_pct}%)`}
                          </span>
                        ) : (
                          "--"
                        )}
                      </td>
                      <td>
                        {r.elder_passed ? (
                          <span className="scr-elder-pass">✓ SHORT SETUP</span>
                        ) : r.weekly_trend_down === false ? (
                          <span className="scr-fail" title="Weekly tide is up, not down">tide up</span>
                        ) : r.divergence_class && !r.volume_confirmed ? (
                          <span className="scr-fail" title="Divergence found but volume rose on the up-move">vol veto</span>
                        ) : (
                          "--"
                        )}
                      </td>
                    </>
                  )}
                </tr>
              ))}
              {shownRows.length === 0 && (
                <tr>
                  <td colSpan={job?.elder_screen ? 12 : 9} style={{ textAlign: "center", color: "var(--ink-soft)" }}>
                    {!job
                      ? "Run a scan above to see results here."
                      : job.elder_screen && elderOnly && passingCount > 0
                        ? "No Elder setups today -- divergence patterns are meant to be rare, this is a normal \"nothing to trade\" result. Uncheck \"Elder setups only\" to see why each Level-1 candidate didn't qualify (weekly tide up, or no divergence found)."
                        : showOnlyPassing && rows.length > 0
                          ? "No symbols passed the filters -- try widening the ATR%/turnover range, or uncheck \"Show passing only\"."
                          : "No results yet."}
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
