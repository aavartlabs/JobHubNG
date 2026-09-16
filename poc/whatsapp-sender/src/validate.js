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
  const digits = phone.replace(/[^0-9]/g, "");
  if (digits.length < 7 || digits.length > 15) {
    return { valid: false, error: "phone does not look like a valid number" };
  }
  return { valid: true, phone, message };
}
