/**
 * Validates a POST /send request body. Kept as a pure function (no HTTP,
 * no Baileys) so it's trivially testable without needing a live socket.
 */
export function validateSendPayload(body) {
  if (typeof body !== "object" || body === null) {
    return { valid: false, error: "request body must be a JSON object" };
  }
  const { phone, message } = body;
  if (typeof phone !== "string" || phone.trim() === "") {
    return { valid: false, error: "phone is required" };
  }
  if (typeof message !== "string" || message.trim() === "") {
    return { valid: false, error: "message is required" };
  }
  // Optional "+", then a country code that never starts with 0, 7-15 digits in all.
  // Spaces, dashes, dots and brackets are tolerated; letters are not silently dropped.
  const compact = phone.trim().replace(/[\s().-]/g, "");
  if (!/^\+?[1-9][0-9]{6,14}$/.test(compact)) {
    return { valid: false, error: "phone does not look like a valid number" };
  }
  return { valid: true, phone, message };
}
