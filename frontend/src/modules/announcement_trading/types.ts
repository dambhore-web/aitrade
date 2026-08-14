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
