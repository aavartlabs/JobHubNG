/* Pure helpers for app.ts's save buttons; tested under `node --test`
   (../test/saving.test.mjs). */

/** The form action after a toggle: /jobs/<id>/save <-> /jobs/<id>/unsave. */
export function savedAction(action: string, saved: boolean): string {
  return action.replace(/\/(save|unsave)$/, saved ? "/unsave" : "/save");
}

/** The button's label after a toggle, keeping the job title after the colon. */
export function savedLabel(label: string, saved: boolean): string {
  return label.replace(/^(Saved|Save job)/, saved ? "Saved" : "Save job");
}
