export interface TradingSettings {
  variety: string;
  order_type: string;
  product_type: string;
  hours_back: number;
  amount: number;
  gtt_stop_pct: number;
  gtt_target_pct: number;
  nse_app_id: string;
  nse_it: string;
  telegram_enabled: boolean;
  updated_utc: string | null;
}

export interface AccountStatus {
  "Zerodha ID"?: string;
  MULTIPLIER?: number;
  ENABLED?: unknown;
  "LOGIN STATUS"?: unknown;
  "EQUITY MARGIN"?: number;
  PNL?: unknown;
}

export interface SessionStatus {
  connected: boolean;
  account_count: number;
  accounts: AccountStatus[];
  session_file_mtime: number | null;
}

export interface TradeEntryCreate {
  announcement_id?: number | null;
  announcement_snapshot?: string | null;
  symbol: string;
  exchange?: string;
  transaction_type?: string;
  amount?: number | null;
  quantity?: number | null;
  stop_loss_pct?: number | null;
  target_pct?: number | null;
  order_type?: string | null;
  product_type?: string | null;
  variety?: string | null;
  notes?: string | null;
}

export interface TradeEntry extends TradeEntryCreate {
  id: number;
  status: "draft" | "placed" | "failed";
  order_result: string | null;
  created_utc: string;
  placed_utc: string | null;
}

export interface TradeEntriesResponse {
  entries: TradeEntry[];
}

export interface LoginAccountStatus {
  status: "pending" | "running" | "success" | "failed";
  message: string;
}

export interface LoginJobStatus {
  running: boolean;
  accounts: Record<string, LoginAccountStatus>;
  error: string | null;
}

export interface ActivityItem {
  id: number;
  ts_utc: string;
  symbol: string | null;
  category: string | null;
  sentiment: string | null;
  text_snippet: string | null;
  skipped: number;
  skip_reason: string | null;
  order_placed: number;
  quantity: number | null;
  current_price: number | null;
  trade_entry_id: number | null;
}

export interface ActivityResponse {
  items: ActivityItem[];
}

export interface AutoLoopStatus {
  running: boolean;
  last_cycle_utc: string | null;
  last_error: string | null;
  state_bse: number | null;
  state_nse: number | null;
  processed_count: number;
  bse_error: string | null;
  nse_error: string | null;
}
