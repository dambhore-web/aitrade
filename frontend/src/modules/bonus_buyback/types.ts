export interface AuthStatus {
  authenticated: boolean;
}

export interface ExtractionRequest {
  start_date: string;
  end_date: string;
  remove_negative: boolean;
  remove_after_market: boolean;
}

export interface ExtractionCreateResponse {
  id: string;
}

export interface ClassifiedRow {
  symbol: string | null;
  desc: string | null;
  an_dt: string | null;
  sentiment: string | null;
  category: string | null;
  qualifies: boolean;
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
  rows: ClassifiedRow[];
  appended_count: number;
}

export interface ExistingRow {
  symbol: string | null;
  an_dt: string | null;
  pred_bert: string | null;
}

export interface ExistingListResponse {
  rows: ExistingRow[];
}
