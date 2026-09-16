"""Match active alert subscriptions against newly-inserted jobs."""
import sqlite3
from dataclasses import dataclass


@dataclass
class Match:
    subscription_id: int
    job_id: int
    phone_number: str
    job_title: str
    job_location: str | None


def find_matches(conn: sqlite3.Connection, new_job_ids: list[int]) -> list[Match]:
    if not new_job_ids:
        return []

    placeholders = ",".join("?" * len(new_job_ids))
    jobs = conn.execute(
        f"SELECT id, title, location FROM jobs WHERE id IN ({placeholders})",
        new_job_ids,
    ).fetchall()

    subscriptions = conn.execute(
        "SELECT id, phone_number, title_keyword, location_keyword FROM alert_subscriptions WHERE is_active = 1"
    ).fetchall()

    matches: list[Match] = []
    for job in jobs:
        job_title = (job["title"] or "").lower()
        job_location = (job["location"] or "").lower()
        for sub in subscriptions:
            title_kw = (sub["title_keyword"] or "").strip().lower()
            location_kw = (sub["location_keyword"] or "").strip().lower()
            if title_kw and title_kw not in job_title:
                continue
            if location_kw and location_kw not in job_location:
                continue
            matches.append(Match(
                subscription_id=sub["id"],
                job_id=job["id"],
                phone_number=sub["phone_number"],
                job_title=job["title"],
                job_location=job["location"],
            ))
    return matches
