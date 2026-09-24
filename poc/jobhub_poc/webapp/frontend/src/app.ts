/* Small enhancements for the server-rendered jobs pages (templates/jobs.html, job.html).
   Everything works without this script; it only makes it smoother. */

import { isJobsListReferrer } from "./back";
import { isPlainClick, nextRowIndex, selectionUrl } from "./split";

/** PC split view (Tailwind `lg`, >= 1024px): clicking a job loads it into the pane beside
    the list instead of opening its page. The URL gets ?sel=<id> via replaceState -- not a
    new history entry -- so Back still leaves the list rather than stepping through every
    job looked at. Below `lg` nothing is intercepted: rows open the job page as before. */
function initSplitView(): void {
  const pane = document.getElementById("job-pane");
  const list = document.getElementById("job-list");
  if (!pane || !list) return;
  const wide = window.matchMedia("(min-width: 1024px)");
  let inFlight: AbortController | null = null;

  async function select(row: HTMLAnchorElement): Promise<void> {
    const id = row.dataset.jobId;
    if (!id || !pane || !list) return;
    list.querySelectorAll('[aria-current="true"]').forEach((el) => el.removeAttribute("aria-current"));
    row.setAttribute("aria-current", "true");
    window.history.replaceState(window.history.state, "", selectionUrl(window.location.href, id));
    inFlight?.abort();
    const controller = new AbortController();
    inFlight = controller;
    pane.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(`/jobs/${id}/panel`, {
        credentials: "same-origin",
        headers: { Accept: "text/html" },
        signal: controller.signal,
      });
      if (!response.ok && response.status !== 404) throw new Error(`HTTP ${response.status}`);
      pane.innerHTML = await response.text(); // our own server-rendered, escaped fragment
      pane.scrollTop = 0;
    } catch (error) {
      if ((error as Error).name === "AbortError") return;
      window.location.href = row.href; // couldn't load it here: open the job's page instead
    } finally {
      if (inFlight === controller) pane.removeAttribute("aria-busy");
    }
  }

  list.addEventListener("click", (event) => {
    if (!wide.matches || !isPlainClick(event)) return;
    const row = (event.target as Element).closest<HTMLAnchorElement>("a.job-row");
    if (!row) return;
    event.preventDefault();
    void select(row);
  });

  list.addEventListener("keydown", (event) => {
    if (!wide.matches || (event.key !== "ArrowDown" && event.key !== "ArrowUp")) return;
    const rows = Array.from(list.querySelectorAll<HTMLAnchorElement>("a.job-row"));
    const current = rows.indexOf(document.activeElement as HTMLAnchorElement);
    if (current < 0) return;
    event.preventDefault();
    const next = rows[nextRowIndex(current, event.key === "ArrowDown" ? 1 : -1, rows.length)];
    if (next && next !== rows[current]) {
      next.focus();
      void select(next);
    }
  });
}

/** Filters: apply a dropdown as soon as it changes, and keep empty fields out of the URL
    so shared/bookmarked list URLs stay short. */
function initFilters(): void {
  const form = document.getElementById("filter-form") as HTMLFormElement | null;
  if (!form) return;
  form.querySelectorAll("select").forEach((select) => {
    select.addEventListener("change", () => form.requestSubmit());
  });
  form.addEventListener("submit", () => {
    form.querySelectorAll<HTMLInputElement | HTMLSelectElement>("input[name], select[name]").forEach((field) => {
      const isDefault = field.value.trim() === "" || (field.name === "posted_within" && field.value === "0");
      if (isDefault) field.disabled = true; // disabled fields aren't submitted
    });
  });
}

/** Back to jobs: when the user came here from the list, go back in history instead --
    the browser then restores the list exactly as it was, scroll position included. The
    link's own href (/jobs?<same filters>#job-<id>) is the fallback, e.g. when the job
    was opened from an alert message. */
function initBackLinks(): void {
  const cameFromList = isJobsListReferrer(document.referrer, window.location.origin);
  document.querySelectorAll<HTMLAnchorElement>("a.back-link").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (cameFromList && window.history.length > 1) {
        event.preventDefault();
        window.history.back();
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initFilters();
  initBackLinks();
  initSplitView();
});
