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
