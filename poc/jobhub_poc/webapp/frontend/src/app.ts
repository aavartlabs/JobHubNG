import { POSTED_WITHIN_OPTIONS, postedLabel } from "./jobs_query";

interface Job {
  id: number;
  title: string;
  company_name: string | null;
  location: string | null;
  employment_type: string | null;
  is_remote: boolean;
  first_seen_at: string;
  posted_at: string | null;
}

/** Only from /api/jobs/<id>, which requires a signed-in, verified user. */
interface JobDetails extends Job {
  description: string | null;
  apply_url: string | null;
}

/** 401/403 bodies from /api/jobs/<id>: where to send the person instead. */
interface GateResponse {
  code: "LOGIN_REQUIRED" | "VERIFY_REQUIRED";
  login_url?: string;
  verify_url?: string;
}

interface JobsResponse {
  jobs: Job[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

type SortKey = "freshness" | "posted" | "title";

interface State {
  title: string;
  location: string;
  sort: SortKey;
  postedWithin: number;
  page: number;
  pageSize: number;
}

const state: State = {
  title: "",
  location: "",
  sort: "freshness",
  postedWithin: 0,
  page: 1,
  pageSize: 10,
};

// Rendered by templates/jobs.html from the server's view of the session, so Apply can
// send a signed-out visitor to login without first opening (and closing) a new tab.
const access = document.getElementById("jobs-app")?.dataset.access ?? "anonymous";

function escapeHtml(value: string): string {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function renderRows(jobs: Job[], startIndex: number): string {
  if (jobs.length === 0) {
    return `<tr><td colspan="6" class="empty">No jobs match the current filters.</td></tr>`;
  }
  return jobs
    .map(
      (job, i) => `<tr>
        <td class="serial">${startIndex + i}</td>
        <td>${escapeHtml(job.title)}</td>
        <td>${escapeHtml(job.company_name ?? "")}</td>
        <td>${escapeHtml(job.location ?? "")}</td>
        <td class="posted" title="${escapeHtml(formatDate(job.posted_at ?? job.first_seen_at))}">${escapeHtml(postedLabel(job.posted_at, job.first_seen_at))}</td>
        <td class="actions">
          <button type="button" class="details-button" data-job-id="${job.id}">Details</button>
          <button type="button" class="apply-button" data-job-id="${job.id}">Apply &rarr;</button>
        </td>
      </tr>`,
    )
    .join("");
}

function loginUrlFor(jobId: number): string {
  return `/login?next=${encodeURIComponent(`/jobs?job=${jobId}`)}`;
}

/** Follows a 401/403 gate response; returns true if it navigated away. */
async function followGate(response: Response): Promise<boolean> {
  if (response.status !== 401 && response.status !== 403) return false;
  let body: GateResponse | null = null;
  try {
    body = (await response.json()) as GateResponse;
  } catch {
    body = null;
  }
  window.location.href = body?.verify_url ?? body?.login_url ?? "/login";
  return true;
}

function renderDetails(job: JobDetails): string {
  const description = job.description
    ? `<div class="description-text">${escapeHtml(job.description)}</div>`
    : "<p><em>No description available for this posting.</em></p>";
  const apply = job.apply_url
    ? `<button type="button" class="apply-button" data-job-id="${job.id}">Apply on employer's site &rarr;</button>`
    : "";
  return `<div class="job-detail-head">
      <h2>${escapeHtml(job.title)}</h2>
      <button type="button" id="close-details" aria-label="Close details">&times;</button>
    </div>
    <p class="job-detail-meta">${escapeHtml([job.company_name, job.location].filter(Boolean).join(" \u00b7 "))}</p>
    ${description}
    ${apply}`;
}

async function showDetails(jobId: number): Promise<void> {
  const panel = document.getElementById("job-detail");
  if (!panel) return;
  let response: Response;
  try {
    response = await fetch(`/api/jobs/${jobId}`, { credentials: "same-origin", headers: { Accept: "application/json" } });
  } catch {
    return;
  }
  if (await followGate(response)) return;
  if (!response.ok) {
    panel.innerHTML = `<p class="error">That job is no longer available.</p>`;
    panel.hidden = false;
    return;
  }
  const job = (await response.json()) as JobDetails;
  panel.innerHTML = renderDetails(job);
  panel.hidden = false;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
  document.getElementById("close-details")?.addEventListener("click", () => {
    panel.hidden = true;
  });
  bindApplyButtons(panel);
}

async function applyTo(jobId: number): Promise<void> {
  if (access === "anonymous") {
    window.location.href = loginUrlFor(jobId);
    return;
  }
  // Opened synchronously inside the click so popup blockers allow it, then pointed at
  // the employer once the click is logged and the URL is known.
  const tab = window.open("about:blank", "_blank");
  let response: Response;
  try {
    response = await fetch(`/api/jobs/${jobId}/apply-click`, { method: "POST", credentials: "same-origin" });
  } catch {
    tab?.close();
    return;
  }
  if (await followGate(response)) {
    tab?.close();
    return;
  }
  if (!response.ok) {
    tab?.close();
    return;
  }
  const { apply_url: applyUrl } = (await response.json()) as { apply_url: string };
  if (tab) {
    tab.opener = null;
    tab.location.href = applyUrl;
  } else {
    window.location.href = applyUrl;
  }
}

function bindApplyButtons(root: ParentNode): void {
  root.querySelectorAll<HTMLButtonElement>(".apply-button").forEach((btn) => {
    btn.addEventListener("click", () => void applyTo(Number(btn.dataset.jobId)));
  });
}

function renderPagination(data: JobsResponse): string {
  const prevDisabled = data.page <= 1 ? "disabled" : "";
  const nextDisabled = data.page >= data.total_pages ? "disabled" : "";
  return `
    <button type="button" id="prev-page" ${prevDisabled}>&larr; Prev</button>
    <span class="page-indicator">Page ${data.page} of ${data.total_pages}</span>
    <button type="button" id="next-page" ${nextDisabled}>Next &rarr;</button>
  `;
}

async function loadJobs(): Promise<void> {
  const tbody = document.getElementById("jobs-body");
  const countEl = document.getElementById("jobs-count");
  const paginationEl = document.getElementById("pagination");
  if (!tbody) return;

  const params = new URLSearchParams();
  if (state.title) params.set("title", state.title);
  if (state.location) params.set("location", state.location);
  params.set("sort", state.sort);
  if (state.postedWithin) params.set("posted_within", String(state.postedWithin));
  params.set("page", String(state.page));
  params.set("page_size", String(state.pageSize));

  let response: Response;
  try {
    response = await fetch(`/api/jobs?${params.toString()}`, {
      headers: { Accept: "application/json" },
    });
  } catch {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">Could not reach the server. Try reloading the page.</td></tr>`;
    return;
  }

  if (response.status === 302 || response.redirected) {
    window.location.href = "/login";
    return;
  }
  if (!response.ok) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">Error loading jobs (HTTP ${response.status}).</td></tr>`;
    return;
  }

  let data: JobsResponse;
  try {
    data = (await response.json()) as JobsResponse;
  } catch {
    window.location.href = "/login";
    return;
  }

  state.page = data.page;
  const start = data.total === 0 ? 0 : (data.page - 1) * data.page_size + 1;
  tbody.innerHTML = renderRows(data.jobs, start);
  if (countEl) {
    const end = Math.min(data.page * data.page_size, data.total);
    countEl.textContent = `Showing ${start}-${end} of ${data.total} job${data.total === 1 ? "" : "s"}`;
  }
  if (paginationEl) paginationEl.innerHTML = renderPagination(data);

  tbody.querySelectorAll<HTMLButtonElement>(".details-button").forEach((btn) => {
    btn.addEventListener("click", () => void showDetails(Number(btn.dataset.jobId)));
  });
  bindApplyButtons(tbody);

  document.getElementById("prev-page")?.addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      void loadJobs();
    }
  });
  document.getElementById("next-page")?.addEventListener("click", () => {
    if (state.page < data.total_pages) {
      state.page += 1;
      void loadJobs();
    }
  });
}

function init(): void {
  const form = document.getElementById("filter-form") as HTMLFormElement | null;
  const titleInput = document.getElementById("title-input") as HTMLInputElement | null;
  const locationInput = document.getElementById("location-input") as HTMLInputElement | null;
  const sortSelect = document.getElementById("sort-select") as HTMLSelectElement | null;
  const pageSizeSelect = document.getElementById("page-size-select") as HTMLSelectElement | null;
  const postedSelect = document.getElementById("posted-within-select") as HTMLSelectElement | null;
  if (postedSelect) {
    postedSelect.innerHTML = POSTED_WITHIN_OPTIONS.map((o) => `<option value="${o.days}">${o.label}</option>`).join("");
  }

  const applyFiltersAndReload = () => {
    state.title = titleInput?.value.trim() ?? "";
    state.location = locationInput?.value.trim() ?? "";
    const sort = sortSelect?.value;
    state.sort = sort === "title" || sort === "posted" ? sort : "freshness";
    state.postedWithin = Number(postedSelect?.value) || 0;
    state.pageSize = pageSizeSelect ? Number(pageSizeSelect.value) || 10 : 10;
    state.page = 1;
    void loadJobs();
  };

  form?.addEventListener("submit", (e) => {
    e.preventDefault();
    applyFiltersAndReload();
  });
  sortSelect?.addEventListener("change", applyFiltersAndReload);
  postedSelect?.addEventListener("change", applyFiltersAndReload);
  pageSizeSelect?.addEventListener("change", applyFiltersAndReload);

  void loadJobs();

  // Back from login/signup via /jobs?job=<id>: open the job they asked for.
  const deepLinked = Number(new URLSearchParams(window.location.search).get("job"));
  if (Number.isInteger(deepLinked) && deepLinked > 0) void showDetails(deepLinked);
}

document.addEventListener("DOMContentLoaded", init);
