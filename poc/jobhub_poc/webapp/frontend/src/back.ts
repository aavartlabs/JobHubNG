/* Pure helper for app.ts's Back links; tested under `node --test` (../test/back.test.mjs). */

/** True if `referrer` is this site's jobs list (/jobs, any filters) -- not a job page,
    not another site. */
export function isJobsListReferrer(referrer: string, origin: string): boolean {
  if (!referrer) return false;
  let url: URL;
  try {
    url = new URL(referrer);
  } catch {
    return false;
  }
  return url.origin === origin && (url.pathname === "/jobs" || url.pathname === "/jobs/");
}
