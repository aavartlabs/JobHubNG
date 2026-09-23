from datetime import datetime, timezone

import pytest

from jobhub_poc.dates import normalize_posted

FIRST_SEEN = "2026-09-23T06:00:00+00:00"


@pytest.mark.parametrize("raw,expected", [
    # Every shape seen in the live jobs table (2026-09-23 survey).
    ("2026-07-15T18:14:31-04:00", "2026-07-15T22:14:31+00:00"),  # 1174 rows: ISO + offset
    ("2026-08-27", "2026-08-27T00:00:00+00:00"),                 # 1151 rows: date only
    ("1788323485", "2026-09-02T04:31:25+00:00"),                 # 70 rows: epoch seconds
    ("2026-09-15T05:15:57Z", "2026-09-15T05:15:57+00:00"),       # 12 rows: ISO Z
    ("Sep 23, 2026", "2026-09-23T00:00:00+00:00"),               # 1 row
    # Close relatives worth accepting.
    (1788323485, "2026-09-02T04:31:25+00:00"),                   # epoch as int
    ("1788323485000", "2026-09-02T04:31:25+00:00"),              # epoch millis
    ("September 3, 2026", "2026-09-03T00:00:00+00:00"),
    ("2026-09-01T10:00:00", "2026-09-01T10:00:00+00:00"),        # naive -> assumed UTC
    ("  2026-08-27  ", "2026-08-27T00:00:00+00:00"),
])
def test_known_formats_become_utc_iso(raw, expected):
    assert normalize_posted(raw, FIRST_SEEN) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "yesterday", "2026-13-45", "not a date", "12", True])
def test_missing_or_unparseable_is_none(raw):
    assert normalize_posted(raw, FIRST_SEEN) is None


def test_implausibly_old_dates_are_treated_as_unknown():
    assert normalize_posted("1970-01-01", FIRST_SEEN) is None
    assert normalize_posted("0", FIRST_SEEN) is None


def test_a_date_after_we_first_saw_the_job_is_clamped_to_first_seen():
    """A job can't be posted after we already scraped it; that's timezone skew or a
    source bug, and it must not make the job look newer than it is."""
    assert normalize_posted("2026-12-01", FIRST_SEEN) == FIRST_SEEN
    assert normalize_posted("2026-09-23T09:00:00+00:00", FIRST_SEEN) == FIRST_SEEN


def test_first_seen_may_be_a_datetime():
    first_seen = datetime(2026, 9, 23, 6, tzinfo=timezone.utc)
    assert normalize_posted("2026-12-01", first_seen) == "2026-09-23T06:00:00+00:00"
    assert normalize_posted("2026-08-27", first_seen) == "2026-08-27T00:00:00+00:00"
