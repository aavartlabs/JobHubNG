interface Job {
  id: number;
  title: string;
  company_name: string | null;
  location: string | null;
  employment_type: string | null;
  is_remote: boolean;
  apply_url: string | null;
  description: string | null;
  first_seen_at: string;
}

interface JobsResponse {
  jobs: Job[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

type SortKey = "freshness" | "title";

interface State {
  title: string;
  location: string;
  sort: SortKey;
  page: number;
  pageSize: number;
  expandedJobId: number | null;
}

const state: State = {
  title: "",
  location: "",
  sort: "freshness",
  page: 1,
  pageSize: 10,
  expandedJobId: null,
};

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
    .map((job, i) => {
      const apply = job.apply_url
        ? `<a class="apply-link" href="${escapeHtml(job.apply_url)}" target="_blank" rel="noopener">Apply &rarr;</a>`
        : "";
      const isExpanded = state.expandedJobId === job.id;
      const descRow = isExpanded
        ? `<tr class="description-row"><td colspan="6">${
            job.description ? `<div class="description-text">${escapeHtml(job.description)}</div>` : "<em>No description available for this posting.</em>"
          }</td></tr>`
        : "";
      return `<tr>
        <td class="serial">${startIndex + i}</td>
        <td>${escapeHtml(job.title)}</td>
        <td>${escapeHtml(job.company_name ?? "")}</td>
        <td>${escapeHtml(job.location ?? "")}</td>
        <td>${formatDate(job.first_seen_at)}</td>
        <td class="actions">
          <button type="button" class="details-toggle" data-job-id="${job.id}">${isExpanded ? "Hide" : "Details"}</button>
          ${apply}
        </td>
      </tr>${descRow}`;
    })
    .join("");
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

  tbody.querySelectorAll<HTMLButtonElement>(".details-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const jobId = Number(btn.dataset.jobId);
      state.expandedJobId = state.expandedJobId === jobId ? null : jobId;
      void loadJobs();
    });
  });

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

  const applyFiltersAndReload = () => {
    state.title = titleInput?.value.trim() ?? "";
    state.location = locationInput?.value.trim() ?? "";
    state.sort = sortSelect && sortSelect.value === "title" ? "title" : "freshness";
    state.pageSize = pageSizeSelect ? Number(pageSizeSelect.value) || 10 : 10;
    state.page = 1;
    state.expandedJobId = null;
    void loadJobs();
  };

  form?.addEventListener("submit", (e) => {
    e.preventDefault();
    applyFiltersAndReload();
  });
  sortSelect?.addEventListener("change", applyFiltersAndReload);
  pageSizeSelect?.addEventListener("change", applyFiltersAndReload);

  void loadJobs();
}

document.addEventListener("DOMContentLoaded", init);
