import type { ReactNode } from "react";

/** Shared card wrapper for a page's major sections -- added 2026-08-17
 * after a trader pointed out sections only being separated by an <h2>
 * with no real visual boundary made the whole page "look merged". Every
 * section now gets a consistent bordered/shadowed card with a distinct
 * header band, matching the exact look Dashboard's own module cards
 * already used (`--surface`/`--border`/`--radius`/`--shadow` -- tokens
 * that already existed, just hadn't been applied to page sections yet).
 *
 * Collapsible sections (Manual Trade Entry, Settings) manage their own
 * open/closed state internally rather than through this component (they
 * need a live draft-count/session badge in the header, which would mean
 * prop-drilling a query result up through the page) -- but their own
 * `.trading-settings` card uses the identical CSS (shared/components.css)
 * so the visual language matches everywhere regardless of which one
 * renders it. */
export default function Section({
  title,
  headerRight,
  children,
}: {
  title: string;
  headerRight?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="page-section">
      <div className="page-section-header">
        <h2>{title}</h2>
        {headerRight}
      </div>
      <div className="page-section-body">{children}</div>
    </section>
  );
}
