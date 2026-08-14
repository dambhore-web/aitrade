import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ColorType,
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { apiGet } from "../../shared/api";
import type {
  CandlesResponse,
  EquityStatus,
  LatestPricesResponse,
  SignalsResponse,
  WatchlistResponse,
} from "./types";
import "./equity.css";

export default function EquityTradingPage() {
  const [symbol, setSymbol] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const status = useQuery({
    queryKey: ["equity", "status"],
    queryFn: () => apiGet<EquityStatus>("/equity/status"),
    refetchInterval: 15000,
  });

  const watchlist = useQuery({
    queryKey: ["equity", "watchlist"],
    queryFn: () => apiGet<WatchlistResponse>("/equity/watchlist"),
  });

  useEffect(() => {
    if (!symbol && watchlist.data?.symbols.length) {
      setSymbol(watchlist.data.symbols[0]);
    }
  }, [watchlist.data, symbol]);

  const candles = useQuery({
    queryKey: ["equity", "candles", symbol],
    queryFn: () => apiGet<CandlesResponse>(`/equity/candles?symbol=${symbol}&limit=300`),
    enabled: !!symbol,
  });

  const signals = useQuery({
    queryKey: ["equity", "signals", symbol],
    queryFn: () => apiGet<SignalsResponse>(`/equity/signals?symbol=${symbol}&limit=50`),
    enabled: !!symbol,
  });

  const latestPrices = useQuery({
    queryKey: ["equity", "latest-prices"],
    queryFn: () => apiGet<LatestPricesResponse>("/equity/latest-prices"),
    refetchInterval: 5000,
  });

  // Chart setup -- runs once.
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "#ffffff" }, textColor: "#333" },
      grid: { vertLines: { color: "#ececf6" }, horzLines: { color: "#ececf6" } },
      height: 460,
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#168736",
      downColor: "#C4122F",
      borderUpColor: "#168736",
      borderDownColor: "#C4122F",
      wickUpColor: "#168736",
      wickDownColor: "#C4122F",
    });
    chartRef.current = chart;
    seriesRef.current = series;

    const resize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Candle data + signal markers -- matches dashboard.py's plot_candle_chart:
  // green/red candles, SELL (down, red) / COVER (up, green) markers at the
  // signal's price/time.
  useEffect(() => {
    const series = seriesRef.current;
    if (!series || !candles.data) return;

    series.setData(
      candles.data.candles.map((c) => ({
        time: c.ts as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    );
    chartRef.current?.timeScale().fitContent();

    const markers: SeriesMarker<Time>[] = (signals.data?.signals ?? [])
      .map((s) => ({
        time: s.ts as UTCTimestamp,
        position: s.signal === "COVER" ? ("belowBar" as const) : ("aboveBar" as const),
        color: s.signal === "COVER" ? "#34D399" : "#F87171",
        shape: s.signal === "COVER" ? ("arrowUp" as const) : ("arrowDown" as const),
        text: s.signal,
      }))
      .sort((a, b) => (a.time as number) - (b.time as number));
    createSeriesMarkers(series, markers);
  }, [candles.data, signals.data]);

  const collectorLive = !!status.data?.latest_price_utc;

  return (
    <div className="page">
      <h1>Equity Trading — Indicator Signals</h1>
      <p className="status-line">
        {status.data ? (
          <>
            {status.data.watchlist_count} symbols watched — last candle{" "}
            {status.data.latest_candle_utc ? new Date(status.data.latest_candle_utc).toLocaleString() : "n/a"}
            {" — "}
            {collectorLive ? "live collector running" : "collector not currently streaming (historical data only)"}
          </>
        ) : (
          "Loading status..."
        )}
      </p>

      <div className="equity-layout">
        <label className="symbol-select-label">
          Symbol
          <select value={symbol ?? ""} onChange={(e) => setSymbol(e.target.value)}>
            {(watchlist.data?.symbols ?? []).map((s) => (
              <option key={s} value={s}>
                {s}
                {latestPrices.data?.prices[s] ? ` — ${latestPrices.data.prices[s].ltp.toFixed(2)}` : ""}
              </option>
            ))}
          </select>
        </label>

        <div className="chart-container" ref={containerRef} />

        <h2>Recent signals — {symbol}</h2>
        <div className="table-scroll">
          <table className="signals-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Signal</th>
                <th>Price</th>
                <th>Meta</th>
              </tr>
            </thead>
            <tbody>
              {(signals.data?.signals ?? []).map((s) => (
                <tr key={s.id}>
                  <td>{s.dt_ist}</td>
                  <td className={`sig-${s.signal.toLowerCase()}`}>{s.signal}</td>
                  <td>{s.close}</td>
                  <td>{s.meta}</td>
                </tr>
              ))}
              {signals.data?.signals.length === 0 && (
                <tr>
                  <td colSpan={4}>No signals yet for this symbol.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
