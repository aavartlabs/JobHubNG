/* Pure helpers for the jobs page's "posted" column and filter. No DOM; tested under
   `node --test` (../test/jobs_query.test.mjs). */

/** Values /api/jobs accepts for posted_within (routes_api._POSTED_WITHIN_DAYS); 0 = any. */
export const POSTED_WITHIN_OPTIONS: { days: number; label: string }[] = [
  { days: 0, label: "Posted any time" },
  { days: 1, label: "Posted in the last 24h" },
  { days: 3, label: "Posted in the last 3 days" },
  { days: 7, label: "Posted in the last week" },
  { days: 30, label: "Posted in the last month" },
];

const DAY_MS = 86_400_000;

function age(iso: string, now: Date): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const days = Math.floor((now.getTime() - then.getTime()) / DAY_MS);
  if (days < 1) return "today";
  if (days < 14) return `${days}d ago`;
  if (days < 60) return `${Math.floor(days / 7)}w ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

/** "3d ago" from the source's posted date; if it has none, "seen 3d ago" from when we
    first found the job -- the same fallback the API's filter and sort use. */
export function postedLabel(postedAt: string | null, firstSeenAt: string, now: Date = new Date()): string {
  if (postedAt) return age(postedAt, now);
  const seen = age(firstSeenAt, now);
  return seen ? `seen ${seen}` : "";
}
