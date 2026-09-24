/* Small enhancements for the server-rendered jobs pages (templates/jobs.html, job.html).
   Everything works without this script; it only makes it smoother. */

import { isJobsListReferrer } from "./back";

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
});
