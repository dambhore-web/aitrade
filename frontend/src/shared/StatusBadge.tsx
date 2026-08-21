export type LoopState = "live" | "paper" | "stopped" | "error";

const LABEL: Record<LoopState, string> = {
  live: "LIVE",
  paper: "PAPER",
  stopped: "STOPPED",
  error: "ERROR",
};

/** Small reusable status pill -- live/paper/stopped/error are the only
 * states, matching what every module's own /status endpoint already
 * exposes (running + mode). Used by the sidebar nav dots and the
 * dashboard's module cards so the same visual language means the same
 * thing everywhere. */
export default function StatusBadge({ state, label }: { state: LoopState; label?: string }) {
  return (
    <span className={`status-badge ${state}`}>
      <span className="dot" />
      {label ?? LABEL[state]}
    </span>
  );
}
