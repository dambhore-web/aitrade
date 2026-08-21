export interface AuthStatus {
  authenticated: boolean;
}

export interface ExtractionRequest {
  start_date: string;
  end_date: string;
  remove_negative: boolean;
  remove_after_market: boolean;
  compute_price_reaction: boolean;
}

export interface ExtractionCreateResponse {
  id: string;
}

export interface NewsRow {
  symbol: string | null;
  desc: string | null;
  an_dt: string | null;
  attchmntFile: string | null;
  sentiment: string | null;
  open: number | null;
  high: number | null;
  low: number | null;
  gain: number | null;
  max_high_candle: number | null;
  max_percentage: number | null;
  category: string | null;
  symbol_exist: string | null;
}

export type JobStatus = "running" | "done" | "error";

export interface ExtractionStatusResponse {
  id: string;
  status: JobStatus;
  error: string | null;
  start_date: string;
  end_date: string;
  log_tail: string[];
  row_count: number;
  rows: NewsRow[];
}

export interface BonusBuybackAppendResponse {
  appended_count: number;
}
