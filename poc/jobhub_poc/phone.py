"""One rule for every phone number that becomes a WhatsApp address: "+", a country code
that never starts with 0, 7-15 digits in all (E.164). Separators are stripped first.

A bare national number ("9902065845") or a "+0..." prefix would be sent to some other
country's number or to no WhatsApp account at all -- the 2026-09-23 OTP that "never
arrived". Mirrors frontend/src/phone.ts and auth-service's isValidPhoneNumber.
"""
import re

_SEPARATORS = re.compile(r"[\s().-]")
_E164 = re.compile(r"^\+[1-9][0-9]{6,14}$")


def normalize_e164(value):
    """The number in +<digits> form, or None if it isn't one."""
    compact = _SEPARATORS.sub("", value or "")
    return compact if _E164.match(compact) else None
