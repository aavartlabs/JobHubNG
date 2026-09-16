interface Job {
  id: number;
  title: string;
  company_name: string | null;
  location: string | null;
  employment_type: string | null;
  is_remote: boolean;
  apply_url: string | null;
  first_seen_at: string;
}

interface JobsResponse {
  count: number;
  jobs: Job[];
}

type SortKey = "freshness" | "title";

function escapeHtml(value: string): string {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

function renderRows(jobs: Job[]): string {
  if (jobs.length === 0) {
    return `<tr><td colspan="5">No jobs match the current filters.</td></tr>`;
  }
  return jobs
    .map((job) => {
      const apply = job.apply_url
        ? `<a href="${escapeHtml(job.apply_url)}" target="_blank" rel="noopener">Apply</a>`
        : "";
      return `<tr>
        <td>${escapeHtml(job.title)}</td>
        <td>${escapeHtml(job.company_name ?? "")}</td>
        <td>${escapeHtml(job.location ?? "")}</td>
        <td>${escapeHtml(job.first_seen_at)}</td>
        <td>${apply}</td>
      </tr>`;
    })
    .join("");
}

async function loadJobs(title: string, location: string, sort: SortKey): Promise<void> {
  const tbody = document.getElementById("jobs-body");
  const countEl = document.getElementById("jobs-count");
  if (!tbody) return;

  const params = new URLSearchParams();
  if (title) params.set("title", title);
  if (location) params.set("location", location);
  params.set("sort", sort);

  let response: Response;
  try {
    response = await fetch(`/api/jobs?${params.toString()}`, {
      headers: { Accept: "application/json" },
    });
  } catch {
    tbody.innerHTML = `<tr><td colspan="5">Could not reach the server. Try reloading the page.</td></tr>`;
    return;
  }

  if (response.status === 302 || response.redirected) {
    window.location.href = "/login";
    return;
  }
  if (!response.ok) {
    tbody.innerHTML = `<tr><td colspan="5">Error loading jobs (HTTP ${response.status}).</td></tr>`;
    return;
  }

  let data: JobsResponse;
  try {
    data = (await response.json()) as JobsResponse;
  } catch {
    // Most likely we were served the login page HTML instead of JSON (session expired).
    window.location.href = "/login";
    return;
  }

  tbody.innerHTML = renderRows(data.jobs);
  if (countEl) countEl.textContent = `Jobs (${data.count})`;
}

function currentSort(): SortKey {
  const select = document.getElementById("sort-select") as HTMLSelectElement | null;
  return select && select.value === "title" ? "title" : "freshness";
}

function init(): void {
  const form = document.getElementById("filter-form") as HTMLFormElement | null;
  const titleInput = document.getElementById("title-input") as HTMLInputElement | null;
  const locationInput = document.getElementById("location-input") as HTMLInputElement | null;
  const sortSelect = document.getElementById("sort-select") as HTMLSelectElement | null;

  const refresh = () => {
    void loadJobs(titleInput?.value.trim() ?? "", locationInput?.value.trim() ?? "", currentSort());
  };

  form?.addEventListener("submit", (e) => {
    e.preventDefault();
    refresh();
  });
  sortSelect?.addEventListener("change", refresh);

  refresh();
}

document.addEventListener("DOMContentLoaded", init);
