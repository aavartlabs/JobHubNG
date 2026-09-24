/* Small enhancements for the server-rendered jobs pages (templates/jobs.html, job.html).
   Everything works without this script; it only makes it smoother. */

import { isJobsListReferrer } from "./back";
import { fileTooLargeMessage, uploadPercent } from "./upload";
import { savedAction, savedLabel } from "./saving";
import { isPlainClick, nextRowIndex, selectionUrl } from "./split";

/** Save buttons are plain POST forms; this toggles them in place instead of reloading.
    Every button for the same job (list row + pane) is updated together. */
function setSaved(jobId: string, saved: boolean): void {
  document.querySelectorAll<HTMLFormElement>(`form.save-form[data-job-id="${jobId}"]`).forEach((form) => {
    form.action = savedAction(form.action, saved);
    const button = form.querySelector("button");
    if (!button) return;
    button.disabled = false;
    button.setAttribute("aria-pressed", String(saved));
    button.setAttribute("aria-label", savedLabel(button.getAttribute("aria-label") ?? "", saved));
    button.title = saved ? "Saved" : "Save job";
  });
}

function initSaving(): void {
  document.addEventListener("submit", async (event) => {
    const form = event.target as HTMLFormElement;
    if (!form.classList?.contains("save-form")) return;
    event.preventDefault();
    const button = form.querySelector("button");
    if (button) button.disabled = true;
    let response: Response;
    try {
      response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
    } catch {
      form.submit(); // network trouble: fall back to the plain form post
      return;
    }
    if (response.status === 401 || response.status === 403) {
      const body = (await response.json().catch(() => null)) as { url?: string } | null;
      window.location.href = body?.url ?? "/login"; // sign in / verify, then back to the job
      return;
    }
    if (!response.ok) {
      if (button) button.disabled = false;
      return;
    }
    const { saved } = (await response.json()) as { saved: boolean };
    setSaved(form.dataset.jobId ?? "", saved);
  });
}

/** Share: the phone's share sheet where there is one, else copy the link. The buttons are
    rendered hidden and shown here, since neither works without JS. */
function revealShareButtons(root: ParentNode): void {
  root.querySelectorAll<HTMLButtonElement>(".share-btn").forEach((button) => {
    button.hidden = false;
  });
}

function initSharing(): void {
  revealShareButtons(document);
  document.addEventListener("click", async (event) => {
    const button = (event.target as Element).closest<HTMLButtonElement>(".share-btn");
    if (!button) return;
    const url = button.dataset.shareUrl ?? window.location.href;
    const title = button.dataset.shareTitle ?? document.title;
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ title, text: `${title} — JobsHub`, url });
      } catch {
        // cancelled by the user: nothing to do
      }
      return;
    }
    const status = button.closest("header")?.parentElement?.querySelector<HTMLElement>(".share-status");
    if (!status) return;
    try {
      await navigator.clipboard.writeText(url);
      status.textContent = "Link copied";
      status.hidden = false;
      window.setTimeout(() => {
        status.hidden = true;
      }, 2500);
    } catch {
      // No clipboard access: show the link to copy by hand, and leave it there.
      status.textContent = url;
      status.hidden = false;
    }
  });
}

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
      revealShareButtons(pane);
      pollPendingMatches(pane);
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

/** "Your match" while the job is being analysed: ask again every few seconds (for up to
    three minutes) and swap in the result. Works in the PC pane after it's swapped too. */
function pollPendingMatches(root: ParentNode): void {
  root.querySelectorAll<HTMLElement>("[data-match-pending]").forEach((card) => {
    const url = card.dataset.matchUrl;
    if (!url || card.dataset.polling) return;
    card.dataset.polling = "1";
    const started = Date.now();
    const check = async (): Promise<void> => {
      if (!card.isConnected || Date.now() - started > 180_000) return;
      try {
        const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "text/html" } });
        if (response.status === 200) {
          card.outerHTML = await response.text();
          return;
        }
      } catch {
        // try again next round
      }
      window.setTimeout(() => void check(), 5000);
    };
    window.setTimeout(() => void check(), 4000);
  });
}

/** /profile review form: "Use: <value>" buttons fill in a suggested value that already
    exists elsewhere in the resume (e.g. the latest job title as the headline). */
function initSuggestions(): void {
  document.querySelectorAll<HTMLButtonElement>("button.suggest-fill").forEach((button) => {
    button.addEventListener("click", () => {
      const field = document.querySelector<HTMLInputElement | HTMLTextAreaElement>(`[name="${button.dataset.field}"]`);
      if (!field) return;
      field.value = button.dataset.value ?? "";
      field.focus();
      button.textContent = "✓ Filled in — save to keep it";
      button.disabled = true;
    });
  });
}

/** /profile upload: refuse an oversized file before sending it (it would travel all the way
    to the server only to be turned away), and show progress while a real upload is sent. */
function initResumeUpload(): void {
  const form = document.getElementById("resume-form") as HTMLFormElement | null;
  if (!form) return;
  const input = form.querySelector<HTMLInputElement>('input[type="file"]');
  const button = form.querySelector<HTMLButtonElement>('button[type="submit"]');
  const errorEl = document.getElementById("resume-client-error");
  const maxBytes = Number(form.dataset.maxBytes) || 0;
  const tooBig = (): string | null => {
    const file = input?.files?.[0];
    return file && maxBytes && file.size > maxBytes ? fileTooLargeMessage(file.size, maxBytes) : null;
  };
  input?.addEventListener("change", () => {
    const problem = tooBig();
    if (errorEl) {
      errorEl.textContent = problem ?? "";
      errorEl.hidden = !problem;
    }
  });
  const bar = document.getElementById("resume-progress") as HTMLProgressElement | null;
  const barWrap = document.getElementById("resume-progress-wrap");
  const barText = document.getElementById("resume-progress-text");
  const buttonLabel = button?.textContent ?? "Upload";
  const showError = (message: string): void => {
    if (errorEl) {
      errorEl.textContent = message;
      errorEl.hidden = false;
    }
    if (barWrap) barWrap.hidden = true;
    if (button) {
      button.disabled = false;
      button.textContent = buttonLabel;
    }
  };

  // Sent with XMLHttpRequest, the one browser API that reports upload progress. The server
  // answers as it does for the plain form: a redirect to /profile on success, the profile
  // page with an error message otherwise.
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (errorEl) errorEl.hidden = true;
    const problem = tooBig();
    if (problem) {
      showError(problem);
      return;
    }
    if (button) {
      button.disabled = true;
      button.textContent = "Uploading…";
    }
    if (bar) bar.value = 0;
    if (barText) barText.textContent = "Uploading… 0%";
    if (barWrap) barWrap.hidden = false;

    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.action);
    xhr.upload.addEventListener("progress", (e) => {
      const percent = uploadPercent(e.loaded, e.lengthComputable ? e.total : 0);
      if (bar) bar.value = percent;
      if (barText) barText.textContent = percent >= 100 ? "Uploaded — checking your file…" : `Uploading… ${percent}%`;
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        window.location.href = xhr.responseURL || "/profile"; // redirect already followed: /profile
        return;
      }
      const page = new DOMParser().parseFromString(xhr.responseText, "text/html");
      const message = page.querySelector("main .error")?.textContent?.trim();
      showError(message || `Upload failed (HTTP ${xhr.status}). Please try again.`);
    });
    xhr.addEventListener("error", () => showError("Upload failed — check your connection and try again."));
    xhr.send(new FormData(form));
  });
}

/** /profile while the resume is being read: check the task every few seconds and reload
    when it's done (or failed), so the review form appears without a manual refresh. */
function initTaskPolling(): void {
  const status = document.getElementById("parse-status");
  const taskId = status?.dataset.taskId;
  if (!status || !taskId) return;
  const check = async (): Promise<void> => {
    try {
      const response = await fetch(`/ai/tasks/${taskId}`, { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (response.ok) {
        const task = (await response.json()) as { status: string; ai_online: boolean };
        if (task.status === "done" || task.status === "failed") {
          window.location.reload();
          return;
        }
        if (!task.ai_online) {
          status.textContent = "Our AI helper is offline right now. Your resume is saved and will be read as soon as it's back — you can leave this page.";
        }
      }
    } catch {
      // network blip: try again next round
    }
    window.setTimeout(() => void check(), 4000);
  };
  window.setTimeout(() => void check(), 3000);
}

document.addEventListener("DOMContentLoaded", () => {
  initFilters();
  initBackLinks();
  initSplitView();
  initSaving();
  initSharing();
  initTaskPolling();
  initResumeUpload();
  initSuggestions();
  pollPendingMatches(document);
});
