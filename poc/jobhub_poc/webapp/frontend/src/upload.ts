/* Pure helper for app.ts's resume upload check; tested under `node --test`
   (../test/upload.test.mjs). */

const MB = 1024 * 1024;

/** Whole-number percent for the upload bar, 0-100 (0 when the total isn't known yet). */
export function uploadPercent(loaded: number, total: number): number {
  if (!total || total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((loaded / total) * 100)));
}

/** "That file is 6.2 MB; the limit is 5 MB. Try a smaller PDF or a DOCX." */
export function fileTooLargeMessage(size: number, maxBytes: number): string {
  const mb = (n: number): string => (n / MB).toFixed(n % MB === 0 ? 0 : 1);
  return `That file is ${mb(size)} MB; the limit is ${mb(maxBytes)} MB. Try a smaller PDF or a DOCX.`;
}
