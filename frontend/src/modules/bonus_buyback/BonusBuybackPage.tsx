import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../shared/api";
import Section from "../../shared/Section";
import { usePersistedJobId } from "../../shared/usePersistedJobId";
import type {
  AuthStatus,
  ExistingListResponse,
  ExtractionCreateResponse,
  ExtractionRequest,
  ExtractionStatusResponse,
} from "./types";
import "./bonus_buyback.css";

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}
function daysAgoIso(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export default function BonusBuybackPage() {
  const authStatus = useQuery({
    queryKey: ["bonus-buyback", "auth-status"],
    queryFn: () => apiGet<AuthStatus>("/bonus-buyback/auth/status"),
    refetchInterval: 10000,
  });

  const [startDate, setStartDate] = useState(daysAgoIso(7));
  const [endDate, setEndDate] = useState(todayIso());
  const [removeNegative, setRemoveNegative] = useState(true);
  const [removeAfterMarket, setRemoveAfterMarket] = useState(true);
  const [jobId, setJobId] = usePersistedJobId("bonus-buyback");

  const existing = useQuery({
    queryKey: ["bonus-buyback", "existing"],
    queryFn: () => apiGet<ExistingListResponse>("/bonus-buyback/existing"),
    enabled: !!authStatus.data?.authenticated,
  });

  const createJob = useMutation({
    mutationFn: () =>
      apiPost<ExtractionCreateResponse>("/bonus-buyback/jobs", {
        start_date: startDate,
        end_date: endDate,
        remove_negative: removeNegative,
        remove_after_market: removeAfterMarket,
      } satisfies ExtractionRequest),
    onSuccess: (res) => setJobId(res.id),
  });

  const jobStatus = useQuery({
    queryKey: ["bonus-buyback", "job", jobId],
    queryFn: () => apiGet<ExtractionStatusResponse>(`/bonus-buyback/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      if (query.state.data?.status === "running") return 2000;
      return false;
    },
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

  const job = jobStatus.data;
  const running = createJob.isPending || job?.status === "running";

  if (authStatus.isLoading) return <div className="page">Checking Kite session...</div>;

  if (!authStatus.data?.authenticated) {
    return (
      <div className="page">
        <h1>Bonus / Buyback Download</h1>
        <div className="banner banner-error">
          No Kite session -- generate a token first on the Announcement Trading page, then come back here.
          This tool uses that same shared session.
        </div>
      </div>
    );
  }

  return (
    <div className="page bb-page">
      <h1>Bonus / Buyback Download</h1>

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
          <div className="field-wide">
            <button className="primary-button" type="submit" disabled={running}>
              {running && <span className="spinner" />}
              {running ? "Running..." : "Run & Append"}
            </button>
          </div>
          {createJob.isError && (
            <p className="banner banner-error field-wide">{(createJob.error as Error).message}</p>
          )}
        </form>
      </Section>

      {job && (
        <Section
          title="Run Log"
          headerRight={<span className="section-status">{job.status} -- {job.row_count} record(s)</span>}
        >
          <div className="log-panel">
            {job.log_tail.map((line, i) => (
              <div key={i}>{line}</div>
            ))}
          </div>

          {job.error && <p className="banner banner-error" style={{ marginTop: "0.75rem" }}>{job.error}</p>}

          {job.status === "done" && (
            <div className="bb-appended-banner">
              Appended {job.appended_count} new bonus/buyback row{job.appended_count === 1 ? "" : "s"} to
              bonus_buyback.csv.
              {existing.data && ` (List now has ${existing.data.rows.length} entries.)`}
              {job.appended_count > 0 && (
                <button type="button" className="secondary-button" style={{ marginLeft: "1rem" }} onClick={() => existing.refetch()}>
                  Refresh existing list below
                </button>
              )}
            </div>
          )}
        </Section>
      )}

      <Section title={`This Run's Classified Announcements (${job?.row_count ?? 0})`}>
        <div className="table-scroll">
          <table className="entries-table bb-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Description</th>
                <th>Announced</th>
                <th>Sentiment</th>
                <th>Category (BERT)</th>
                <th>Qualifies</th>
              </tr>
            </thead>
            <tbody>
              {(job?.rows ?? []).map((r, i) => (
                <tr key={i} className={r.qualifies ? "bb-qualifies" : ""}>
                  <td>{r.symbol}</td>
                  <td>{r.desc}</td>
                  <td>{r.an_dt}</td>
                  <td>{r.sentiment}</td>
                  <td>{r.category}</td>
                  <td>{r.qualifies ? "bonus/buyback" : ""}</td>
                </tr>
              ))}
              {(!job || job.rows.length === 0) && (
                <tr className="bb-empty-row">
                  <td colSpan={6}>
                    {job && job.status === "done" ? "No matching announcements for this range/filters." : "Run an extraction above to see results here."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title={`Current Exclusion List (${existing.data?.rows.length ?? "..."} entries)`}>
        <div className="table-scroll">
          <table className="entries-table bb-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Announced</th>
                <th>Category</th>
              </tr>
            </thead>
            <tbody>
              {(existing.data?.rows ?? []).map((r, i) => (
                <tr key={i}>
                  <td>{r.symbol}</td>
                  <td>{r.an_dt}</td>
                  <td>{r.pred_bert}</td>
                </tr>
              ))}
              {existing.data && existing.data.rows.length === 0 && (
                <tr className="bb-empty-row">
                  <td colSpan={3}>Nothing logged yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}
