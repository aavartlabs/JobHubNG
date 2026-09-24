/* Pure helper for app.ts's resume upload check; tested under `node --test`
   (../test/upload.test.mjs). */

const MB = 1024 * 1024;

/** "That file is 6.2 MB; the limit is 5 MB. Try a smaller PDF or a DOCX." */
export function fileTooLargeMessage(size: number, maxBytes: number): string {
  const mb = (n: number): string => (n / MB).toFixed(n % MB === 0 ? 0 : 1);
  return `That file is ${mb(size)} MB; the limit is ${mb(maxBytes)} MB. Try a smaller PDF or a DOCX.`;
}
