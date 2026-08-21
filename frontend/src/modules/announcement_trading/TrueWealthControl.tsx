import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../shared/api";
import StatusBadge from "../../shared/StatusBadge";
import type { TrueWealthStatus } from "./types";
import "./trading.css";

/** Start/stop for the native TrueWealth (TrueData wealth backend) BSE
 * announcement source -- a second, independent poller from the NSE/BSE
 * auto-loop above, racing it for the same announcements. Whichever source
 * sees a given announcement first wins (see truewealth_source.py); both
 * feed the same activity log, distinguished by the TRUEWEALTH_BSE source
 * pill in the table above. Starting this opens a real, visible Chromium
 * window -- that's intentional (see truewealth_source.py's docstring on
 * why headless wasn't reliable for this site). */
export default function TrueWealthControl() {
  const queryClient = useQueryClient();

  const status = useQuery({
    queryKey: ["announcement-trading", "truewealth-status"],
    queryFn: () => apiGet<TrueWealthStatus>("/announcement-trading/truewealth/status"),
    refetchInterval: 5000,
  });

  const start = useMutation({
    mutationFn: () => apiPost<TrueWealthStatus>("/announcement-trading/truewealth/start"),
    onSuccess: (data) => queryClient.setQueryData(["announcement-trading", "truewealth-status"], data),
  });

  const stop = useMutation({
    mutationFn: () => apiPost<TrueWealthStatus>("/announcement-trading/truewealth/stop"),
    onSuccess: (data) => queryClient.setQueryData(["announcement-trading", "truewealth-status"], data),
  });

  return (
    <div className="auto-loop-control">
      <div className="control-panel">
        <button
          className="start-button"
          onClick={() => start.mutate()}
          disabled={start.isPending || status.data?.running}
        >
          START
        </button>
        <button
          className="stop-button"
          onClick={() => stop.mutate()}
          disabled={stop.isPending || !status.data?.running}
        >
          STOP
        </button>
        <StatusBadge
          state={!status.data?.running ? "stopped" : status.data?.authorized ? "live" : "paper"}
          label={
            !status.data?.running
              ? "Stopped"
              : status.data?.authorized
                ? "Authorized"
                : "Waiting for login session..."
          }
        />
        <span className="processed-count">{status.data?.processed_count ?? 0} processed</span>
      </div>
      {start.isError && <p className="banner banner-error">{(start.error as Error).message}</p>}
      {status.data?.last_error && <p className="banner banner-warning">{status.data.last_error}</p>}
      {status.data?.running && !status.data?.authorized && (
        <p className="field-hint">
          No login session captured yet -- if a visible Chromium window opened and shows a login page,
          log in to TrueWealth there once; the session persists after that.
        </p>
      )}
    </div>
  );
}
