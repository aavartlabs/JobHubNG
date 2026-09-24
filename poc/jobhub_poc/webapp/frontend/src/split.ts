/* Pure helpers for the PC split view (app.ts); tested under `node --test`
   (../test/split.test.mjs). */

/** The current list URL with ?sel=<jobId> set (other params kept, #hash dropped), so a
    reload or a shared link reopens the same job in the pane. */
export function selectionUrl(href: string, jobId: string): string {
  const url = new URL(href);
  url.searchParams.set("sel", jobId);
  url.hash = "";
  return url.pathname + url.search;
}

/** Arrow-key movement through the list: one step, stopping at either end. */
export function nextRowIndex(current: number, delta: number, count: number): number {
  if (count <= 0) return -1;
  return Math.min(count - 1, Math.max(0, current + delta));
}

/** Only a plain left click is taken over; ctrl/cmd/shift/middle-click keep opening the
    job's page in a new tab or window as usual. */
export function isPlainClick(event: { button: number; metaKey: boolean; ctrlKey: boolean; shiftKey: boolean; altKey: boolean }): boolean {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}
