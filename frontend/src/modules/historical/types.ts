export interface AuthStatus {
  authenticated: boolean;
  api_key_configured: boolean;
}

export interface LoginUrlResponse {
  login_url: string;
}

export interface InstrumentsResponse {
  exchange: string;
  symbols: string[];
}

export type Interval =
  | "minute"
  | "3minute"
  | "5minute"
  | "10minute"
  | "15minute"
  | "30minute"
  | "60minute"
  | "day";

export interface JobCreateRequest {
  symbols: string[];
  exchange: string;
  interval: Interval;
  start_date: string;
  end_date: string;
  incremental: boolean;
  continuous: boolean;
  output_dir: string | null;
}

export interface JobCreateResponse {
  id: string;
}

export interface SymbolProgress {
  status: "pending" | "running" | "success" | "failed";
  message: string;
}

export interface JobStatusResponse {
  id: string;
  status: "running" | "done" | "error" | "cancelled";
  error: string | null;
  exchange: string;
  interval: string;
  start_date: string;
  end_date: string;
  output_dir: string;
  progress: Record<string, SymbolProgress>;
  log_tail: string[];
  done_count: number;
  total_count: number;
}
