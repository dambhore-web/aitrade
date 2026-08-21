import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../shared/api";
import Section from "../../shared/Section";
import { usePersistedJobId } from "../../shared/usePersistedJobId";
import type {
  AuthStatus,
  BonusBuybackAppendResponse,
  ExtractionCreateResponse,
  ExtractionRequest,
  ExtractionStatusResponse,
} from "./types";
import "./news_extractor.css";

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function formatGain(v: number | null) {
  if (v === null || v === undefined) return "--";
  return v.toFixed(2);
}

export default function NewsExtractorPage() {
  const queryClient = useQueryClient();

  const authStatus = useQuery({
    queryKey: ["news-extractor", "auth-status"],
    queryFn: () => apiGet<AuthStatus>("/news-extractor/auth/status"),
    refetchInterval: 10000,
  });

  const [startDate, setStartDate] = useState(todayIso());
  const [endDate, setEndDate] = useState(todayIso());
  const [removeNegative, setRemoveNegative] = useState(true);
  const [removeAfterMarket, setRemoveAfterMarket] = useState(true);
  const [runZerodhaAnalysis, setRunZerodhaAnalysis] = useState(true);
  const [jobId, setJobId] = usePersistedJobId("news-extractor");

  const createJob = useMutation({
    mutationFn: () =>
      apiPost<ExtractionCreateResponse>("/news-extractor/jobs", {
        start_date: startDate,
        end_date: endDate,
        remove_negative: removeNegative,
        remove_after_market: removeAfterMarket,
        compute_price_reaction: runZerodhaAnalysis,
      } satisfies ExtractionRequest),
    onSuccess: (res) => setJobId(res.id),
  });

  const jobStatus = useQuery({
    queryKey: ["news-extractor", "job", jobId],
    queryFn: () => apiGet<ExtractionStatusResponse>(`/news-extractor/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1500 : false),
    retry: false,
  });

  // A persisted job id can outlive the job it points to (backend restart
  // clears the in-memory registry) -- clear it once confirmed dead rather
  // than leaving a reference that 404s forever.
  useEffect(() => {
    if (jobStatus.isError && jobId) {
      setJobId(null);
    }
  }, [jobStatus.isError, jobId, setJobId]);

  const appendBonusBuyback = useMutation({
    mutationFn: () => apiPost<BonusBuybackAppendResponse>(`/news-extractor/jobs/${jobId}/append-bonus-buyback`),
  });

  const running = createJob.isPending || jobStatus.data?.status === "running";
  const job = jobStatus.data;

  if (authStatus.isLoading) return <div className="page">Checking Kite session...</div>;

  if (!authStatus.data?.authenticated) {
    return (
      <div className="page">
        <h1>News Extractor</h1>
        <div className="banner banner-error">
          No Kite session -- generate a token first on the Announcement Trading page, then come back here.
          This tool uses that same shared session.
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>News Extractor</h1>

      <Section title="Extraction Settings">
        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            createJob.mutate();
          }}
        >
          <label>
            Start Date
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
          <label>
            End Date
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </label>
          <label className="checkbox-label">
            <input type="checkbox" checked={removeNegative} onChange={(e) => setRemoveNegative(e.target.checked)} />
            Remove Negative Sentiment
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={removeAfterMarket}
              onChange={(e) => setRemoveAfterMarket(e.target.checked)}
            />
            Remove After Market
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={runZerodhaAnalysis}
              onChange={(e) => setRunZerodhaAnalysis(e.target.checked)}
            />
            Run Zerodha Analysis
          </label>

          <div className="field-wide ne-buttons">
            <button className="primary-button" type="submit" disabled={running}>
              {running && <span className="spinner" />}
              {running ? "Running..." : "Run Analysis"}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => jobId && queryClient.invalidateQueries({ queryKey: ["news-extractor", "job", jobId] })}
              disabled={!jobId}
            >
              Refresh Table
            </button>
            {job?.status === "done" &&
              job.rows.some((r) => r.category === "bo_stock_split" || r.category === "buyback") && (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => appendBonusBuyback.mutate()}
                  disabled={appendBonusBuyback.isPending}
                >
                  {appendBonusBuyback.isPending ? "Appending..." : "Append Bonus/Buyback Rows"}
                </button>
              )}
          </div>
          {createJob.isError && (
            <p className="banner banner-error field-wide">{(createJob.error as Error).message}</p>
          )}
        </form>
      </Section>

      <Section
        title="Run Progress"
        headerRight={<span className="section-status">{job ? `${job.status} -- ${job.row_count} record(s)` : "Ready"}</span>}
      >
        <div className="progress-track">
          <div
            className={`progress-fill ${running ? "indeterminate" : ""}`}
            style={{ width: job?.status === "done" ? "100%" : running ? undefined : "0%" }}
          />
        </div>
        <div className="log-panel">
          {(job?.log_tail ?? []).map((line, i) => (
            <div key={i} className={job?.status === "error" && i === job.log_tail.length - 1 ? "log-line-error" : undefined}>
              {line}
            </div>
          ))}
          {!job && <div>Ready.</div>}
        </div>
        {job?.error && <p className="banner banner-error" style={{ marginTop: "0.75rem" }}>{job.error}</p>}
        {appendBonusBuyback.data && (
          <p className="banner banner-warning" style={{ marginTop: "0.75rem" }}>
            Appended {appendBonusBuyback.data.appended_count} new bonus/buyback row(s).
          </p>
        )}
      </Section>

      <Section title={`Results (${job?.row_count ?? 0})`}>
        <div className="table-scroll">
          <table className="entries-table ne-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Description</th>
                <th>Announced</th>
                <th>Attachment</th>
                <th>Sentiment</th>
                <th>Open</th>
                <th>High</th>
                <th>Low</th>
                <th>Gain %</th>
                <th>Max High %</th>
                <th>Category (BERT)</th>
                <th>Symbol Exists</th>
              </tr>
            </thead>
            <tbody>
              {(job?.rows ?? []).map((row, i) => (
                <tr key={i}>
                  <td>{row.symbol}</td>
                  <td>{row.desc}</td>
                  <td>{row.an_dt}</td>
                  <td>
                    {row.attchmntFile ? (
                      <a href={row.attchmntFile} target="_blank" rel="noreferrer">
                        link
                      </a>
                    ) : (
                      "--"
                    )}
                  </td>
                  <td className={row.sentiment === "positive" ? "ne-sentiment-positive" : "ne-sentiment-neutral"}>
                    {row.sentiment}
                  </td>
                  <td>{row.open?.toFixed(2) ?? "--"}</td>
                  <td>{row.high?.toFixed(2) ?? "--"}</td>
                  <td>{row.low?.toFixed(2) ?? "--"}</td>
                  <td className={(row.gain ?? 0) >= 0 ? "ne-gain-pos" : "ne-gain-neg"}>{formatGain(row.gain)}</td>
                  <td>{formatGain(row.max_percentage)}</td>
                  <td>{row.category}</td>
                  <td>{row.symbol_exist}</td>
                </tr>
              ))}
              {job && job.rows.length === 0 && (
                <tr>
                  <td colSpan={12} style={{ textAlign: "center", color: "var(--ink-soft)" }}>
                    No matching announcements for this range/filters.
                  </td>
                </tr>
              )}
              {!job && (
                <tr>
                  <td colSpan={12} style={{ textAlign: "center", color: "var(--ink-soft)" }}>
                    Run an extraction above to see results here.
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
