import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, apiPut } from "../../shared/api";
import type { LoginJobStatus, SessionStatus, TradingSettings } from "./types";
import "./trading.css";

export default function TradingSettingsPanel() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();

  const settings = useQuery({
    queryKey: ["announcement-trading", "settings"],
    queryFn: () => apiGet<TradingSettings>("/announcement-trading/settings"),
  });

  const sessionStatus = useQuery({
    queryKey: ["announcement-trading", "session-status"],
    queryFn: () => apiGet<SessionStatus>("/announcement-trading/session-status"),
    refetchInterval: 30000,
  });

  const [loginPolling, setLoginPolling] = useState(false);
  const loginStatus = useQuery({
    queryKey: ["announcement-trading", "login-status"],
    queryFn: () => apiGet<LoginJobStatus>("/announcement-trading/session/generate/status"),
    refetchInterval: loginPolling ? 2000 : false,
  });

  const generateToken = useMutation({
    mutationFn: () => apiPost<LoginJobStatus>("/announcement-trading/session/generate"),
    onSuccess: () => setLoginPolling(true),
  });

  useEffect(() => {
    if (loginPolling && loginStatus.data && !loginStatus.data.running) {
      setLoginPolling(false);
      queryClient.invalidateQueries({ queryKey: ["announcement-trading", "session-status"] });
    }
  }, [loginPolling, loginStatus.data, queryClient]);

  const [form, setForm] = useState<Partial<TradingSettings>>({});
  useEffect(() => {
    if (settings.data) setForm(settings.data);
  }, [settings.data]);

  const save = useMutation({
    mutationFn: () => apiPut<TradingSettings>("/announcement-trading/settings", form),
    onSuccess: (data) => {
      queryClient.setQueryData(["announcement-trading", "settings"], data);
    },
  });

  const set = <K extends keyof TradingSettings>(key: K, value: TradingSettings[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  return (
    <div className="trading-settings">
      <button className="collapse-toggle" onClick={() => setOpen((o) => !o)}>
        {open ? "▾" : "▸"} Trading settings
        {sessionStatus.data && (
          <span className={sessionStatus.data.connected ? "session-pill session-ok" : "session-pill session-off"}>
            {sessionStatus.data.connected
              ? `${sessionStatus.data.account_count} Kite account${sessionStatus.data.account_count === 1 ? "" : "s"} connected`
              : "No Kite session"}
          </span>
        )}
      </button>

      {open && (
        <div className="settings-body">
          {!sessionStatus.data?.connected && (
            <p className="banner banner-warning">
              No Kite token yet -- generate one below (logs into every account listed in
              Zerodha_Orders.xlsx). No trade, of any kind, can happen without this.
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
              disabled={generateToken.isPending || loginPolling}
            >
              {loginPolling ? "Signing in..." : "Generate Token"}
            </button>
            {loginStatus.data && Object.keys(loginStatus.data.accounts).length > 0 && (
              <ul className="login-progress">
                {Object.entries(loginStatus.data.accounts).map(([id, acct]) => (
                  <li key={id} className={`login-status-${acct.status}`}>
                    {id}: {acct.status}
                    {acct.message ? ` -- ${acct.message}` : ""}
                  </li>
                ))}
              </ul>
            )}
            {loginStatus.data?.error && <p className="banner banner-error">{loginStatus.data.error}</p>}
          </div>

          <div className="settings-grid">
            <label>
              Amount ({"₹"})
              <input
                type="number"
                value={form.amount ?? 0}
                onChange={(e) => set("amount", Number(e.target.value))}
              />
            </label>
            <label>
              Order variety
              <select value={form.variety ?? "regular"} onChange={(e) => set("variety", e.target.value)}>
                <option value="regular">regular</option>
                <option value="co">co</option>
                <option value="bo">bo</option>
              </select>
            </label>
            <label>
              Order type
              <select value={form.order_type ?? "MARKET"} onChange={(e) => set("order_type", e.target.value)}>
                <option value="MARKET">MARKET</option>
                <option value="SL-M">SL-M</option>
                <option value="LIMIT">LIMIT</option>
              </select>
            </label>
            <label>
              Market/product type
              <select
                value={form.product_type ?? "MTF"}
                onChange={(e) => set("product_type", e.target.value)}
              >
                <option value="MTF">MTF</option>
                <option value="MIS">MIS</option>
                <option value="CNC">CNC</option>
              </select>
            </label>
            <label>
              GTT stop loss (%)
              <input
                type="number"
                step="0.01"
                value={form.gtt_stop_pct ?? -0.6}
                onChange={(e) => set("gtt_stop_pct", Number(e.target.value))}
              />
            </label>
            <label>
              GTT target (%)
              <input
                type="number"
                step="0.01"
                value={form.gtt_target_pct ?? 20}
                onChange={(e) => set("gtt_target_pct", Number(e.target.value))}
              />
            </label>
            <label>
              Past hours (news lookback)
              <input
                type="number"
                value={form.hours_back ?? 0}
                onChange={(e) => set("hours_back", Number(e.target.value))}
              />
            </label>
            <label>
              NSE App ID
              <input value={form.nse_app_id ?? ""} onChange={(e) => set("nse_app_id", e.target.value)} />
            </label>
            <label>
              NSE IT
              <input value={form.nse_it ?? ""} onChange={(e) => set("nse_it", e.target.value)} />
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={form.telegram_enabled ?? false}
                onChange={(e) => set("telegram_enabled", e.target.checked)}
              />
              Send messages to Telegram
            </label>
          </div>

          <button className="save-button" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "Saving..." : "SAVE"}
          </button>
          {save.isSuccess && <span className="save-confirm">Data saved!</span>}
          {save.isError && <p className="banner banner-error">{(save.error as Error).message}</p>}
        </div>
      )}
    </div>
  );
}
