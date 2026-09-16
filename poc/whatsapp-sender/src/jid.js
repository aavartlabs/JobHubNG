/**
 * Converts a phone number in any common format (+1 555 123 4567, 15551234567,
 * etc.) to a Baileys/WhatsApp JID. Baileys addresses individual chats as
 * "<digits-only phone number>@s.whatsapp.net".
 */
export function toJid(phoneNumber) {
  const digits = String(phoneNumber).replace(/[^0-9]/g, "");
  return `${digits}@s.whatsapp.net`;
}
