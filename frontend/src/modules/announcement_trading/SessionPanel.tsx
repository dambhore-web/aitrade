import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../shared/api";
import type { LoginJobStatus, SessionStatus } from "./types";
import "./trading.css";

/** Kite session status + Generate Token -- pulled out of
 * TradingSettingsPanel (2026-08-17) and given its own always-visible,
 * uncollapsed section at the very top of the page. It was previously
 * buried inside a collapsed "Trading settings" panel at the bottom,
 * alongside GTT %/amount/order-type fields that really are configure-once
 * -- but a session isn't: Kite tokens expire daily, nothing on this page
 * (START, positions, manual trade entry) works without one, and a trader
 * couldn't find where to create it ("where is the session creation???").
 * Session and Settings are two different kinds of thing; this splits
 * them. */
export default function SessionPanel() {
  const queryClient = useQueryClient();

  const sessionStatus = useQuery({
    queryKey: ["announcement-trading", "session-status"],
    queryFn: () => apiGet<SessionStatus>("/announcement-trading/session-status"),
    refetchInterval: 30000,
  });

  // Polling is driven directly by the query's own last-known `running`
  // value (via the refetchInterval callback), not a separate boolean piece
  // of state -- a prior version used a separate `loginPolling` flag +
  // useEffect pair that could desync from the real job state and leave the
  // spinner stuck forever even after the backend had genuinely finished.
  const loginStatus = useQuery({
    queryKey: ["announcement-trading", "login-status"],
    queryFn: () => apiGet<LoginJobStatus>("/announcement-trading/session/generate/status"),
    refetchInterval: (query) => (query.state.data?.running ? 2000 : false),
  });
  const loginRunning = loginStatus.data?.running ?? false;

  const generateToken = useMutation({
    mutationFn: () => apiPost<LoginJobStatus>("/announcement-trading/session/generate"),
    onSuccess: (data) => {
      // Seed the cache immediately so the refetchInterval above (reading
      // this same cache entry) starts polling right away.
      queryClient.setQueryData(["announcement-trading", "login-status"], data);
    },
  });

  const wasRunningRef = useRef(false);
  useEffect(() => {
    if (wasRunningRef.current && !loginRunning) {
      queryClient.invalidateQueries({ queryKey: ["announcement-trading", "session-status"] });
    }
    wasRunningRef.current = loginRunning;
  }, [loginRunning, queryClient]);

  return (
    <div className="session-panel">
      {sessionStatus.data && (
        <span className={sessionStatus.data.connected ? "session-pill session-ok" : "session-pill session-off"}>
          {sessionStatus.data.connected
            ? `${sessionStatus.data.account_count} Kite account${sessionStatus.data.account_count === 1 ? "" : "s"} connected`
            : "No Kite session"}
        </span>
      )}

      {!sessionStatus.data?.connected && (
        <p className="banner banner-warning">
          No Kite token yet -- generate one below (logs into every account listed in Zerodha_Orders.xlsx).
          No trade, of any kind, can happen without this.
        </p>
      )}
      {sessionStatus.data?.connected && (
        <ul className="account-list">
          {sessionStatus.data.accounts.map((a) => (
            <li key={a["Zerodha ID"] as string}>
              {a["Zerodha ID"]} -- margin {"₹"}
              {(a["EQUITY MARGIN"] ?? 0).toLocaleString()} -- multiplier {a.MULTIPLIER ?? 1}
            </li>
          ))}
        </ul>
      )}

      <div className="token-section">
        <button
          className="generate-token-button"
          onClick={() => {
            if (
              window.confirm(
                "This logs into every account in Zerodha_Orders.xlsx using its stored credentials (real browser automation). Continue?"
              )
            ) {
              generateToken.mutate();
            }
          }}
          disabled={generateToken.isPending || loginRunning}
        >
          {(generateToken.isPending || loginRunning) && <span className="spinner" aria-hidden="true" />}
          {generateToken.isPending
            ? "Starting..."
            : loginRunning
              ? "Signing in -- this can take 10-30s per account..."
              : "Generate Token"}
        </button>
        {generateToken.isError && <p className="banner banner-error">{(generateToken.error as Error).message}</p>}
        {loginStatus.isError && loginRunning && (
          <p className="banner banner-error">
            Lost contact with the backend while checking progress: {(loginStatus.error as Error).message}
          </p>
        )}
        {loginStatus.data && Object.keys(loginStatus.data.accounts).length > 0 && (
          <ul className="login-progress">
            {Object.entries(loginStatus.data.accounts).map(([id, acct]) => (
              <li key={id} className={`login-status-${acct.status}`}>
                {(acct.status === "running" || acct.status === "pending") && (
                  <span className="spinner" aria-hidden="true" />
                )}
                {id}: {acct.status}
                {acct.message ? ` -- ${acct.message}` : ""}
              </li>
            ))}
          </ul>
        )}
        {loginStatus.data?.error && <p className="banner banner-error">{loginStatus.data.error}</p>}
      </div>
    </div>
  );
}
