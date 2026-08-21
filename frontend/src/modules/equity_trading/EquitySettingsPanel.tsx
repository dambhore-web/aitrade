import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPut } from "../../shared/api";
import type { EquitySettings, EquityStrategy } from "./types";
import "./equity.css";

/** Amount-per-trade for the equity auto-trading loop -- scanner.py
 * converts this into a share quantity at order time (max(1, int(amount //
 * current_price))), replacing the old flat "every symbol trades 1 share"
 * design. Read fresh by scanner_loop.py on every signal (see its
 * _get_amount()), so saving here takes effect on the very next signal --
 * no restart of the loop needed, unlike editing new_trade_tool/config.py's
 * AMOUNT constant would require. */
export default function EquitySettingsPanel() {
  const queryClient = useQueryClient();

  const settings = useQuery({
    queryKey: ["equity-auto-trading", "settings"],
    queryFn: () => apiGet<EquitySettings>("/equity-auto-trading/settings"),
  });

  const [amount, setAmount] = useState<number>(10000);
  const [strategy, setStrategy] = useState<EquityStrategy>("wisestock");
  useEffect(() => {
    if (settings.data) {
      setAmount(settings.data.amount);
      setStrategy(settings.data.strategy);
    }
  }, [settings.data]);

  const save = useMutation({
    mutationFn: () => apiPut<EquitySettings>("/equity-auto-trading/settings", { amount, strategy }),
    onSuccess: (data) => {
      queryClient.setQueryData(["equity-auto-trading", "settings"], data);
    },
  });

  return (
    <div className="equity-settings-panel">
      <div className="settings-grid">
        <label>
          Strategy
          <select value={strategy} onChange={(e) => setStrategy(e.target.value as EquityStrategy)}>
            <option value="wisestock">WiseStockTrader (VWAP crossover)</option>
            <option value="breakout">Breakout (Opening-Range)</option>
          </select>
          <span className="field-hint">
            Only one strategy trades at a time. Switching here takes effect on the next signal --
            positions already open stay tracked and exit normally under whichever strategy opened
            them.
          </span>
        </label>
        <label>
          Amount per trade ({"₹"})
          <input
            type="number"
            min={1}
            step={500}
            value={amount}
            onChange={(e) => setAmount(Number(e.target.value))}
          />
          <span className="field-hint">
            Each SELL entry buys as many whole shares as this amount covers at the current price
            (rounded down, minimum 1 share). A ₹500 stock and a ₹5000 stock now risk roughly the
            same rupee amount instead of both trading a flat share count.
          </span>
        </label>
      </div>

      <button className="save-button" onClick={() => save.mutate()} disabled={save.isPending}>
        {save.isPending && <span className="spinner" aria-hidden="true" />}
        {save.isPending ? "Saving..." : "SAVE"}
      </button>
      {save.isSuccess && <span className="save-confirm">Data saved!</span>}
      {save.isError && <p className="banner banner-error">{(save.error as Error).message}</p>}
    </div>
  );
}
