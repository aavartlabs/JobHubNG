"""Normalises EverJobs' `datePosted` into one comparable form.

The source field is unreliable (see schema.sql): a 2026-09-23 survey of the live jobs
table found ISO datetimes with offsets, bare dates, Unix epoch seconds, ISO "Z" strings,
"Sep 23, 2026", and missing values. Everything parseable becomes a UTC ISO string;
anything else is None, and callers fall back to our own first_seen.

Standard library only -- pi05's warehouse ingest imports this.
"""
from datetime import datetime, timezone

# Before this, a "posted" date is noise (epoch 0, placeholder years), not a real posting.
_EARLIEST_PLAUSIBLE = datetime(2000, 1, 1, tzinfo=timezone.utc)
_TEXT_FORMATS = ("%b %d, %Y", "%B %d, %Y")


def _as_utc(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return _as_utc(datetime.fromisoformat(value))


def _parse(raw):
    if isinstance(raw, bool):  # bool is an int subclass; never a timestamp
        return None
    if isinstance(raw, (int, float)):
        raw = str(int(raw))
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()

    if text.isdigit():
        if len(text) == 13:  # epoch milliseconds
            return datetime.fromtimestamp(int(text) / 1000, timezone.utc)
        if len(text) == 10 or text == "0":  # epoch seconds
            return datetime.fromtimestamp(int(text), timezone.utc)
        return None

    try:
        # Python 3.11+ fromisoformat accepts "Z" and bare dates.
        return _as_utc(datetime.fromisoformat(text))
    except ValueError:
        pass
    for fmt in _TEXT_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def normalize_posted(raw, first_seen):
    """UTC ISO string for `raw`, or None if it's missing, unparseable or implausible.

    Never later than `first_seen` (ISO string or datetime): a job can't be posted after
    we already scraped it, so a later date is skew or a source bug and is clamped.
    """
    posted = _parse(raw)
    if posted is None or posted < _EARLIEST_PLAUSIBLE:
        return None
    seen = _as_utc(first_seen)
    return min(posted, seen).isoformat()
