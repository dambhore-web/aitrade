import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, API_BASE_URL } from "../../shared/api";
import Section from "../../shared/Section";
import { usePersistedJobId } from "../../shared/usePersistedJobId";
import type {
  AuthStatus,
  Interval,
  InstrumentsResponse,
  JobCreateRequest,
  JobCreateResponse,
  JobStatusResponse,
} from "./types";
import "./historical.css";

/** Parses a symbols CSV client-side -- matches the legacy
 * load_symbols_from_file()'s own rule (pd.read_csv, so the first row is
 * always the header): a 'tradingsymbol'/'symbol' column if present
 * (case-insensitive), else the first column; upper-cased, de-duplicated,
 * order preserved. */
function parseSymbolsCsv(text: string): string[] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length < 2) return [];

  const splitRow = (line: string) => line.split(",").map((c) => c.trim());
  const header = splitRow(lines[0]).map((h) => h.toLowerCase());
  const symbolColIdx = header.findIndex((h) => h === "tradingsymbol" || h === "symbol");
  const colIdx = symbolColIdx !== -1 ? symbolColIdx : 0;

  const seen = new Set<string>();
  const out: string[] = [];
  for (const line of lines.slice(1)) {
    const cell = splitRow(line)[colIdx];
    if (!cell) continue;
    const s = cell.trim().toUpperCase();
    if (s && !seen.has(s)) {
      seen.add(s);
      out.push(s);
    }
  }
  return out;
}

const INTERVALS: Interval[] = [
  "day", "minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute",
];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}
function daysAgoIso(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export default function HistoricalPage() {
  const queryClient = useQueryClient();
  const authStatus = useQuery({
    queryKey: ["historical", "auth-status"],
    queryFn: () => apiGet<AuthStatus>("/historical/auth/status"),
    refetchInterval: 10000,
  });

  const [exchange, setExchange] = useState("NSE");
  const [symbolsText, setSymbolsText] = useState("");
  const [csvFileName, setCsvFileName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [interval, setIntervalValue] = useState<Interval>("minute");
  const [startDate, setStartDate] = useState(daysAgoIso(30));
  const [endDate, setEndDate] = useState(todayIso());
  const [incremental, setIncremental] = useState(true);
  const [outputDir, setOutputDir] = useState("");
  const [jobId, setJobId] = usePersistedJobId("historical");

  function handleCsvFile(file: File) {
    const reader = new FileReader();
    reader.onload = () => {
      const symbols = parseSymbolsCsv(String(reader.result ?? ""));
      setSymbolsText(symbols.join(", "));
      setCsvFileName(`${file.name} (${symbols.length} symbols)`);
    };
    reader.readAsText(file);
  }

  const instruments = useQuery({
    queryKey: ["historical", "instruments", exchange],
    queryFn: () => apiGet<InstrumentsResponse>(`/historical/instruments?exchange=${exchange}`),
    enabled: !!authStatus.data?.authenticated,
    staleTime: 60 * 60 * 1000,
  });

  const createJob = useMutation({
    mutationFn: () =>
      apiPost<JobCreateResponse>("/historical/jobs", {
        symbols: symbolsText
          .split(/[,\n\r\t ]+/)
          .map((s) => s.trim().toUpperCase())
          .filter(Boolean),
        exchange,
        interval,
        start_date: startDate,
        end_date: endDate,
        incremental,
        continuous: false,
        output_dir: outputDir.trim() || null,
      } satisfies JobCreateRequest),
    onSuccess: (res) => setJobId(res.id),
  });

  const jobStatus = useQuery({
    queryKey: ["historical", "job", jobId],
    queryFn: () => apiGet<JobStatusResponse>(`/historical/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1500 : false),
    retry: false,
  });

  // A persisted job id can outlive the job it points to (backend restart
  // clears the in-memory registry) -- clear it once that's confirmed
  // rather than leaving a dead reference that 404s forever.
  useEffect(() => {
    if (jobStatus.isError && jobId) {
      setJobId(null);
    }
  }, [jobStatus.isError, jobId, setJobId]);

  const cancelJob = useMutation({
    mutationFn: () => apiPost<JobStatusResponse>(`/historical/jobs/${jobId}/cancel`),
    // Written straight into the query cache rather than waiting on the next
    // poll -- the button should read "Cancelling..." for one request, not
    // up to 1.5s of still saying "Cancel" after it's already been clicked.
    onSuccess: (data) => queryClient.setQueryData(["historical", "job", jobId], data),
  });

  if (authStatus.isLoading) return <div className="page">Checking Kite session...</div>;

  if (!authStatus.data?.authenticated) {
    return (
      <div className="page">
        <h1>Historical Data Extractor</h1>
        <div className="banner banner-error">
          No Kite session -- generate a token first on the Announcement Trading page (Window 1),
          then come back here. This tool uses that same shared session.
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Historical Data Extractor</h1>

      <Section title="Download Settings" headerRight={<span className="status-line" style={{ margin: 0 }}>Shared Kite session from Announcement Trading</span>}>
        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            createJob.mutate();
          }}
        >
          <label>
            Exchange
            <select value={exchange} onChange={(e) => setExchange(e.target.value)}>
              <option value="NSE">NSE</option>
              <option value="BSE">BSE</option>
            </select>
          </label>

          <label>
            Interval
            <select value={interval} onChange={(e) => setIntervalValue(e.target.value as Interval)}>
              {INTERVALS.map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </label>

          <label>
            Start date
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>

          <label>
            End date
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </label>

          <label className="checkbox-label">
            <input type="checkbox" checked={incremental} onChange={(e) => setIncremental(e.target.checked)} />
            Incremental (skip dates already downloaded)
          </label>

          <label>
            Download path (optional)
            <input
              type="text"
              placeholder={`Default: aitrade\\data\\historical`}
              value={outputDir}
              onChange={(e) => setOutputDir(e.target.value)}
            />
            <span className="field-hint">
              One CSV per symbol, always appended and de-duplicated -- leave blank to use the default.
            </span>
          </label>

          <label className="field-wide">
            Symbols CSV file
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleCsvFile(file);
              }}
            />
            {csvFileName && <span className="field-hint">Loaded: {csvFileName}</span>}
          </label>

          <label className="field-wide">
            Symbols (comma/newline separated -- or edit what the CSV loaded)
            <textarea
              rows={4}
              placeholder="RELIANCE, TCS, INFY..."
              value={symbolsText}
              onChange={(e) => {
                setSymbolsText(e.target.value);
                setCsvFileName(null);
              }}
            />
            {instruments.data && (
              <span className="field-hint">
                {instruments.data.symbols.length.toLocaleString()} {exchange} symbols available from Kite.
              </span>
            )}
          </label>

          <div className="field-wide">
            <button className="primary-button" type="submit" disabled={createJob.isPending || !symbolsText.trim()}>
              {createJob.isPending && <span className="spinner" />}
              {createJob.isPending ? "Starting..." : "Start download"}
            </button>
          </div>
          {createJob.isError && (
            <p className="banner banner-error field-wide">{(createJob.error as Error).message}</p>
          )}
        </form>
      </Section>

      {jobId && jobStatus.data && (
        <JobProgress
          job={jobStatus.data}
          jobId={jobId}
          onCancel={() => cancelJob.mutate()}
          cancelling={cancelJob.isPending}
        />
      )}
    </div>
  );
}

function JobProgress({
  job,
  jobId,
  onCancel,
  cancelling,
}: {
  job: JobStatusResponse;
  jobId: string;
  onCancel: () => void;
  cancelling: boolean;
}) {
  const entries = Object.entries(job.progress);
  const running = job.status === "running";
  return (
    <Section
      title="Job Progress"
      headerRight={
        <div style={{ display: "flex", alignItems: "center", gap: "0.9rem" }}>
          <span className="section-status">
            {job.status === "running" ? "in progress" : job.status} -- {job.done_count}/{job.total_count}
          </span>
          {running && (
            <button className="secondary-button" onClick={onCancel} disabled={cancelling}>
              {cancelling && <span className="spinner" />}
              {cancelling ? "Cancelling..." : "Cancel"}
            </button>
          )}
        </div>
      }
    >
      <div className="progress-track">
        <div
          className={`progress-fill ${running ? "indeterminate" : ""}`}
          style={{ width: job.status === "done" ? "100%" : running ? undefined : "0%" }}
        />
      </div>
      <p className="field-hint" style={{ marginBottom: "0.75rem" }}>Saving to: {job.output_dir}</p>
      {job.status === "cancelled" && (
        <p className="banner banner-warning">
          Cancelled -- symbols already in progress were left to finish; anything not yet started was stopped.
        </p>
      )}
      {job.error && <p className="banner banner-error">{job.error}</p>}

      <div className="table-scroll">
        <table className="entries-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Status</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([symbol, p]) => (
              <tr key={symbol}>
                <td>{symbol}</td>
                <td className={`status-${p.status}`}>{p.status}</td>
                <td>{p.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {job.done_count > 0 && (
        <a className="download-link" href={`${API_BASE_URL}/historical/jobs/${jobId}/result`}>
          Download results (.zip)
        </a>
      )}
    </Section>
  );
}
