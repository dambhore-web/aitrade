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
import Section from "../../shared/Section";
import EquityAutoLoopControl from "./EquityAutoLoopControl";
import EquityPositionsPanel from "./EquityPositionsPanel";
import EquitySettingsPanel from "./EquitySettingsPanel";
import WatchlistEditor from "./WatchlistEditor";
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
  const [tab, setTab] = useState<"live" | "explorer" | "watchlist">("live");

  return (
    <div className="page">
      <h1>Equity Trading</h1>

      {/* Two different jobs that used to share one continuous scroll --
          split in the Phase 2 nav/UI redesign (see docs/requirements.md):
          watching/controlling the live auto-loop vs. researching any
          watched symbol's chart. Both sections stay mounted (just
          hidden/shown via CSS) rather than conditionally rendered, so the
          chart's one-time setup effect below never has to re-run. */}
      <div className="tab-bar">
        <button className={tab === "live" ? "tab-button active" : "tab-button"} onClick={() => setTab("live")}>
          Live Auto-Trading
        </button>
        <button
          className={tab === "explorer" ? "tab-button active" : "tab-button"}
          onClick={() => setTab("explorer")}
        >
          Symbol Explorer
        </button>
        <button
          className={tab === "watchlist" ? "tab-button active" : "tab-button"}
          onClick={() => setTab("watchlist")}
        >
          Watchlist
        </button>
      </div>

      <div style={{ display: tab === "live" ? "block" : "none" }}>
        <Section title="Status & Control">
          <EquityAutoLoopControl />
        </Section>
        <Section title="Trade Settings">
          <EquitySettingsPanel />
        </Section>
        <Section title="Positions & P&L">
          <EquityPositionsPanel />
        </Section>
      </div>

      <div style={{ display: tab === "watchlist" ? "block" : "none" }}>
        <Section title="Watchlist">
          <WatchlistEditor />
        </Section>
      </div>

      <div style={{ display: tab === "explorer" ? "block" : "none" }}>
        <Section
          title="Symbol Explorer"
          headerRight={
            <span className="status-line" style={{ margin: 0 }}>
              {status.data ? (
                <>
                  {status.data.watchlist_count} symbols watched — last candle{" "}
                  {status.data.latest_candle_utc
                    ? new Date(status.data.latest_candle_utc).toLocaleString()
                    : "n/a"}
                  {" — "}
                  {collectorLive ? "live collector running" : "collector not streaming (historical only)"}
                </>
              ) : (
                "Loading status..."
              )}
            </span>
          }
        >
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
          </div>
        </Section>

        <Section title={`Recent signals — ${symbol ?? ""}`}>
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
        </Section>
      </div>
    </div>
  );
}
