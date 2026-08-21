export interface WatchlistResponse {
  symbols: string[];
}

export interface CandleOut {
  ts: number;
  dt_ist: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandlesResponse {
  symbol: string;
  exchange: string;
  interval: number;
  candles: CandleOut[];
}

export interface SignalOut {
  id: number;
  symbol: string;
  exchange: string;
  interval: number;
  ts: number;
  dt_ist: string;
  signal: string;
  close: number;
  meta: string | null;
  gen_ts: number | null;
  gen_dt_ist: string | null;
}

export interface SignalsResponse {
  signals: SignalOut[];
}

export interface LatestPriceEntry {
  ltp: number;
  ts: number;
}

export interface LatestPricesResponse {
  exchange: string;
  prices: Record<string, LatestPriceEntry>;
}

export interface EquityStatus {
  exchange: string;
  interval: number;
  watchlist_count: number;
  latest_candle_utc: string | null;
  latest_price_utc: string | null;
}

export interface EquityAutoLoopStatus {
  running: boolean;
  mode: "PAPER" | "LIVE" | null;
  last_cycle_utc: string | null;
  last_error: string | null;
  open_positions: number;
  watchlist_count: number;
  last_health_check_utc: string | null;
}

export interface EquityAutoSignalItem {
  id: number;
  symbol: string;
  exchange: string;
  interval: number;
  ts: number;
  dt_ist: string;
  signal: string;
  close: number;
  meta: string | null;
}

export interface EquityAutoSignalsResponse {
  items: EquityAutoSignalItem[];
}

export interface EquityPositionItem {
  zerodha_id: string | null;
  tradingsymbol: string;
  exchange: string;
  product: string;
  quantity: number;
  average_price: number;
  last_price: number;
  pnl: number;
}

export interface EquityPositionsResponse {
  items: EquityPositionItem[];
  total_pnl: number;
}

export type EquityStrategy = "wisestock" | "breakout";

export interface EquitySettings {
  amount: number;
  strategy: EquityStrategy;
  updated_utc: string | null;
}

export interface EquityWatchlistResponse {
  symbols: string[];
}
