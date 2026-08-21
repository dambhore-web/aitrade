export interface BacktestJobCreateRequest {
  symbols: string[] | null;
  start_date: string | null;
  end_date: string | null;
  strategy: "wisestock" | "breakout";
}

export interface BacktestJobCreateResponse {
  id: string;
}

export interface TradeRow {
  Symbol: string;
  Trade: string;
  Date: string;
  Price: number;
  "Ex. date": string;
  "Ex. Price": number;
  "% chg": number;
  Profit: number;
  "% Profit": number;
  Shares: number;
  "Position value": number;
  "Cum. Profit": number;
  "# bars": number;
  "Profit/bar": number | null;
  MAE: number | null;
  MFE: number | null;
  "Scale In/Out": string;
  "Exit reason": string;
}

export interface BacktestSummary {
  trades: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  max_win: number;
  max_loss: number;
}

export interface BacktestJobStatusResponse {
  id: string;
  status: "running" | "done" | "error" | "cancelled";
  error: string | null;
  start_date: string | null;
  end_date: string | null;
  done_count: number;
  total_count: number;
  signal_count: number;
  log_tail: string[];
  summary: BacktestSummary;
  trades: TradeRow[];
}
