export interface AuthStatus {
  authenticated: boolean;
}

export interface ScreenerJobCreateRequest {
  exchange: string;
  lookback_days: number;
  atr_period: number;
  min_price: number;
  min_avg_turnover_cr: number;
  min_atr_pct: number;
  max_atr_pct: number;
  eq_series_only: boolean;
  max_symbols: number | null;
  symbols: string[] | null;
  elder_screen: boolean;
}

export interface ScreenerJobCreateResponse {
  id: string;
}

export interface ScreenerRow {
  symbol: string;
  last_close: number;
  atr: number;
  atr_pct: number;
  hist_vol_pct: number;
  avg_turnover_cr: number;
  avg_volume: number;
  avg_gap_pct: number;
  passes_filters: boolean;
  score: number;
  // Level 2 -- Elder Triple Screen. null = not run for this row (Level 2
  // off, or this row never passed Level 1).
  weekly_trend_down: boolean | null;
  divergence_class: "A" | "B" | null;
  bull_power_shrink_pct: number | null;
  volume_confirmed: boolean | null;
  elder_passed: boolean | null;
}

export interface ScreenerJobStatusResponse {
  id: string;
  status: "running" | "done" | "error" | "cancelled";
  error: string | null;
  exchange: string;
  lookback_days: number;
  min_price: number;
  min_avg_turnover_cr: number;
  min_atr_pct: number;
  max_atr_pct: number;
  elder_screen: boolean;
  done_count: number;
  total_count: number;
  elder_done_count: number;
  elder_total_count: number;
  log_tail: string[];
  rows: ScreenerRow[];
}
