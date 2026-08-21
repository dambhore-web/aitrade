import { useState } from "react";

/** Keeps a tool page's last job id in sessionStorage instead of plain
 * useState -- added 2026-08-17 after "I download historical data, move to
 * another page, and it's vanished". The job itself lives in the backend's
 * in-memory registry (historical/news_extractor/bonus_buyback all keep
 * jobs in a dict keyed by id, never evicted except on a backend restart)
 * and the downloaded files are already safely on disk -- only the
 * browser's own pointer to the job id was fragile: React Router unmounts
 * the page component on navigation, which resets plain useState to its
 * initial value, so coming back showed an empty page even though nothing
 * was actually lost server-side. sessionStorage (not localStorage) so it
 * clears with the tab, matching how jobs themselves don't survive a
 * backend restart either -- an id surviving longer than the job it points
 * to would just mean a confusing 404 on refetch. */
export function usePersistedJobId(pageKey: string): [string | null, (id: string | null) => void] {
  const storageKey = `job-id:${pageKey}`;

  const [jobId, setJobIdState] = useState<string | null>(() => {
    try {
      return sessionStorage.getItem(storageKey);
    } catch {
      return null;
    }
  });

  function setJobId(id: string | null) {
    setJobIdState(id);
    try {
      if (id) sessionStorage.setItem(storageKey, id);
      else sessionStorage.removeItem(storageKey);
    } catch {
      // private browsing / storage disabled -- falls back to plain
      // in-memory state for this session, same as before this fix
    }
  }

  return [jobId, setJobId];
}
