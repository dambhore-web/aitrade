import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPut } from "../../shared/api";
import type { TradingSettings } from "./types";
import "./trading.css";

/** Pure trading-parameter settings (Amount, GTT %, order type/variety/
 * product, NSE app config, Telegram) -- configure-once, revisited rarely,
 * so stays collapsed by default. Session status/Generate Token moved out
 * to SessionPanel.tsx (2026-08-17): unlike these fields, a session isn't
 * "configure once" (Kite tokens expire daily) and everything else on the
 * page depends on it, so it needed its own always-visible section instead
 * of sharing this collapsed one. */
export default function TradingSettingsPanel() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();

  const settings = useQuery({
    queryKey: ["announcement-trading", "settings"],
    queryFn: () => apiGet<TradingSettings>("/announcement-trading/settings"),
  });

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
      </button>

      {open && (
        <div className="settings-body">
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
              Market protection (%)
              <input
                type="number"
                step="0.5"
                min="0"
                max="100"
                value={form.market_protection_pct ?? 3}
                onChange={(e) => set("market_protection_pct", Number(e.target.value))}
              />
              <span className="field-hint">
                How far past the price at order time Zerodha will let a MARKET order fill. Wider = faster
                fills on fresh news, at the cost of accepting a worse price if it's genuinely spiking.
              </span>
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
            {save.isPending && <span className="spinner" aria-hidden="true" />}
            {save.isPending ? "Saving..." : "SAVE"}
          </button>
          {save.isSuccess && <span className="save-confirm">Data saved!</span>}
          {save.isError && <p className="banner banner-error">{(save.error as Error).message}</p>}
        </div>
      )}
    </div>
  );
}
