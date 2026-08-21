import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./api";
import type { LoopState } from "./StatusBadge";

// Minimal shapes -- only the fields the sidebar/dashboard actually read.
// The full types live in each module's own types.ts; duplicated narrowly
// here rather than importing across module boundaries from shared/.
interface AnnouncementAutoStatus {
  running: boolean;
  last_error: string | null;
}
interface AnnouncementPosition {
  quantity: number;
  pnl: number;
}
interface AnnouncementPositions {
  items: AnnouncementPosition[];
  total_pnl: number;
}
interface EquityAutoStatus {
  running: boolean;
  mode: "PAPER" | "LIVE" | null;
  last_error: string | null;
  open_positions: number;
  watchlist_count: number;
}
interface EquitySignalsToday {
  items: unknown[];
}

export function loopState(running: boolean, lastError: string | null, mode?: "PAPER" | "LIVE" | null): LoopState {
  if (lastError) return "error";
  if (!running) return "stopped";
  return mode === "PAPER" ? "paper" : "live";
}

/** Announcement Trading's live status + open positions/P&L -- both cheap,
 * already-existing endpoints. Announcement Trading has no PAPER mode (it
 * always places real orders when running), so its loopState only ever
 * resolves to live/stopped/error. */
export function useAnnouncementStatus() {
  const status = useQuery({
    queryKey: ["dashboard", "announcement", "status"],
    queryFn: () => apiGet<AnnouncementAutoStatus>("/announcement-trading/auto/status"),
    refetchInterval: 5000,
  });
  const positions = useQuery({
    queryKey: ["dashboard", "announcement", "positions"],
    queryFn: () => apiGet<AnnouncementPositions>("/announcement-trading/positions"),
    refetchInterval: status.data?.running ? 8000 : 30000,
  });
  const openCount = (positions.data?.items ?? []).filter((p) => p.quantity !== 0).length;
  return {
    isLoading: status.isLoading,
    running: status.data?.running ?? false,
    state: loopState(status.data?.running ?? false, status.data?.last_error ?? null),
    lastError: status.data?.last_error ?? null,
    openPositions: openCount,
    totalPnl: positions.data?.total_pnl ?? 0,
  };
}

/** Equity Trading's live status, open positions, watchlist size, and
 * today's signal count (the /signals endpoint already defaults to today
 * IST). */
export function useEquityStatus() {
  const status = useQuery({
    queryKey: ["dashboard", "equity", "status"],
    queryFn: () => apiGet<EquityAutoStatus>("/equity-auto-trading/status"),
    refetchInterval: 5000,
  });
  const signals = useQuery({
    queryKey: ["dashboard", "equity", "signals-today"],
    queryFn: () => apiGet<EquitySignalsToday>("/equity-auto-trading/signals?limit=100"),
    refetchInterval: status.data?.running ? 15000 : 60000,
  });
  return {
    isLoading: status.isLoading,
    running: status.data?.running ?? false,
    mode: status.data?.mode ?? null,
    state: loopState(status.data?.running ?? false, status.data?.last_error ?? null, status.data?.mode),
    lastError: status.data?.last_error ?? null,
    openPositions: status.data?.open_positions ?? 0,
    watchlistCount: status.data?.watchlist_count ?? 0,
    signalsToday: signals.data?.items.length ?? 0,
  };
}
