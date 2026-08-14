import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { API_BASE_URL, apiGet, apiPost } from "../../shared/api";
import type {
  AuthStatus,
  Interval,
  InstrumentsResponse,
  JobCreateRequest,
  JobCreateResponse,
  JobStatusResponse,
  LoginUrlResponse,
} from "./types";
import "./historical.css";

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
  });

  const [requestToken, setRequestToken] = useState("");
  const loginMutation = useMutation({
    mutationFn: () => apiPost<AuthStatus>("/historical/auth/session", { request_token: requestToken }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["historical", "auth-status"] });
      setRequestToken("");
    },
  });

  const [exchange, setExchange] = useState("NSE");
  const [symbolsText, setSymbolsText] = useState("");
  const [interval, setIntervalValue] = useState<Interval>("day");
  const [startDate, setStartDate] = useState(daysAgoIso(30));
  const [endDate, setEndDate] = useState(todayIso());
  const [incremental, setIncremental] = useState(true);
  const [jobId, setJobId] = useState<string | null>(null);

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
      } satisfies JobCreateRequest),
    onSuccess: (res) => setJobId(res.id),
  });

  const jobStatus = useQuery({
    queryKey: ["historical", "job", jobId],
    queryFn: () => apiGet<JobStatusResponse>(`/historical/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1500 : false),
  });

  if (authStatus.isLoading) return <div className="page">Checking Kite login...</div>;

  if (!authStatus.data?.api_key_configured) {
    return (
      <div className="page">
        <h1>Historical Data Extractor</h1>
        <div className="banner banner-error">
          KITE_API_KEY / KITE_API_SECRET not set in backend/.env -- add them (from
          https://developers.kite.trade/apps) and restart the backend.
        </div>
      </div>
    );
  }

  if (!authStatus.data.authenticated) {
    return (
      <div className="page">
        <h1>Historical Data Extractor</h1>
        <LoginFlow requestToken={requestToken} setRequestToken={setRequestToken} loginMutation={loginMutation} />
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Historical Data Extractor</h1>
      <p className="status-line">Signed in to Kite for today.</p>

      <form
        className="job-form"
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

        <label className="symbols-field">
          Symbols (comma/newline separated)
          <textarea
            rows={4}
            placeholder="RELIANCE, TCS, INFY..."
            value={symbolsText}
            onChange={(e) => setSymbolsText(e.target.value)}
          />
          {instruments.data && (
            <p className="field-hint">
              {instruments.data.symbols.length.toLocaleString()} {exchange} symbols available from Kite.
            </p>
          )}
        </label>

        <button type="submit" disabled={createJob.isPending || !symbolsText.trim()}>
          {createJob.isPending ? "Starting..." : "Start download"}
        </button>
        {createJob.isError && <p className="banner banner-error">{(createJob.error as Error).message}</p>}
      </form>

      {jobId && jobStatus.data && <JobProgress job={jobStatus.data} jobId={jobId} />}
    </div>
  );
}

function LoginFlow({
  requestToken,
  setRequestToken,
  loginMutation,
}: {
  requestToken: string;
  setRequestToken: (v: string) => void;
  loginMutation: ReturnType<typeof useMutation<AuthStatus, Error, void>>;
}) {
  const loginUrlQuery = useQuery({
    queryKey: ["historical", "login-url"],
    queryFn: () => apiGet<LoginUrlResponse>("/historical/auth/login-url"),
  });

  return (
    <div className="login-flow">
      <p>
        Kite access tokens expire ~6am IST daily -- sign in again each morning before downloading.
      </p>
      <ol>
        <li>
          <a href={loginUrlQuery.data?.login_url} target="_blank" rel="noreferrer">
            Log in to Kite
          </a>{" "}
          (opens in a new tab)
        </li>
        <li>After redirect, copy the <code>request_token</code> value from the URL</li>
        <li>
          Paste it here:{" "}
          <input value={requestToken} onChange={(e) => setRequestToken(e.target.value)} placeholder="request_token" />
          <button
            onClick={() => loginMutation.mutate()}
            disabled={!requestToken || loginMutation.isPending}
          >
            {loginMutation.isPending ? "Signing in..." : "Sign in"}
          </button>
        </li>
      </ol>
      {loginMutation.isError && (
        <p className="banner banner-error">{(loginMutation.error as Error).message}</p>
      )}
    </div>
  );
}

function JobProgress({ job, jobId }: { job: JobStatusResponse; jobId: string }) {
  const entries = Object.entries(job.progress);
  return (
    <div className="job-progress">
      <h2>
        Job {job.status === "running" ? "in progress" : job.status} -- {job.done_count}/{job.total_count}
      </h2>
      {job.error && <p className="banner banner-error">{job.error}</p>}

      <div className="table-scroll">
        <table>
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
    </div>
  );
}
