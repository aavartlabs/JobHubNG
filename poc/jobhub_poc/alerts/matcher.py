"""Which active alerts match which newly-inserted jobs, grouped per alert so each alert
gets one digest. Only ids the loader reported as genuinely new are considered."""
import json
import sqlite3
from dataclasses import dataclass, field

from jobhub_poc.alerts.rules import Rule, rule_matches


@dataclass
class AlertMatch:
    subscription_id: int
    owner_auth_user_id: str
    rule: Rule
    notify_email: bool
    notify_telegram: bool
    jobs: list[dict] = field(default_factory=list)


def rule_from_row(row) -> Rule:
    load = lambda key: tuple(json.loads(row[key] or "[]"))
    return Rule(titles=load("titles"), locations=load("locations"), companies=load("companies"),
                keywords=load("keywords"), work_mode=row["work_mode"])


def find_matches(conn: sqlite3.Connection, new_job_ids: list[int]) -> list[AlertMatch]:
    if not new_job_ids:
        return []
    placeholders = ",".join("?" * len(new_job_ids))
    jobs = [dict(r) for r in conn.execute(
        f"SELECT id, title, company_name, location, description, is_remote FROM jobs WHERE id IN ({placeholders})",
        new_job_ids,
    )]
    matches = []
    for sub in conn.execute("SELECT * FROM alert_subscriptions WHERE is_active = 1 ORDER BY id"):
        rule = rule_from_row(sub)
        matched = [job for job in jobs if rule_matches(rule, job)]
        if matched:
            matches.append(AlertMatch(sub["id"], sub["owner_auth_user_id"], rule,
                                      bool(sub["notify_email"]), bool(sub["notify_telegram"]), matched))
    return matches
