"""Weekly batch: grow skill_aliases (skills.py) from the skills job postings actually use, so
"Terraform Cloud" / "TerraformCloud" or "ReactJS" / "React.js" become one skill.

1. Collect the distinct skills in job readings (job_requirements; job text only -- never
   resumes), each by its current standard name.
2. Group likely variants in code: a one- or two-letter difference (names of 5+ characters),
   one being the other's acronym (IaC <-> infrastructure as code), or one containing the
   other plus a filler word. Pairs in skills.DIFFERENT or rejected at /admin/skills are never
   grouped.
3. Ask the LLM, per group, which names are the same skill and which is the standard one.
4. Keep a merge only if the LLM says so AND the pair has that textual link, then store it
   (source=llm).

Runs through llm.generate(task="jobs"): the local model on prod; nothing when AI is paused.
Never at page time.

    python -m jobhub_poc.ai.skill_index [--max-groups N] [--dry-run]
"""
import argparse
import json
import sys
from datetime import datetime, timezone

from jobhub_poc import db, skills
from jobhub_poc.ai import llm

SCHEMA = {"type": "object", "properties": {"same": {"type": "array", "items": {"type": "object", "properties": {
    "standard": {"type": "string"}, "variants": {"type": "array", "items": {"type": "string"}}},
    "required": ["standard", "variants"]}}}, "required": ["same"]}
PROMPT = """These are names of skills from job postings. Some may be spellings of the SAME skill
(e.g. "ReactJS" and "React.js"; "IaC" and "infrastructure as code"). Others only look alike
and are DIFFERENT skills (e.g. "Java" and "JavaScript"; "C" and "C#"; "SQL" and "NoSQL").
List only the groups you are sure are the same skill, each with its most standard name.
Leave out anything you are unsure about.

Names: {names}
"""


def _distance(a, b, limit=2):
    """Edit distance, or limit+1 when larger (early exit)."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _acronym(short, long):
    words = [w for w in long.split() if w not in ("of", "and", "as", "the", "a", "an", "for", "to")]
    return len(words) >= 2 and short.replace(" ", "") == "".join(w[0] for w in words)


def linked(a, b):
    """The textual link a merge must have besides the LLM's word."""
    if frozenset((a, b)) in skills.DIFFERENT:
        return False
    short, long = sorted((a, b), key=len)
    if min(len(a), len(b)) >= 5 and _distance(a, b) <= 2:
        return True
    if _acronym(short, long):
        return True
    return short.replace(" ", "") == long.replace(" ", "")  # "terraformcloud" vs "terraform cloud"


def collect(conn, index):
    names = {}
    for (data,) in conn.execute("SELECT data_json FROM job_requirements"):
        d = json.loads(data)
        for s in (d.get("required_skills") or []) + (d.get("preferred_skills") or []):
            c = index.canonical(s)
            if 2 <= len(c) <= 50:
                names[c] = names.get(c, 0) + 1
    return names


def groups(names, rejected=frozenset(), max_size=8):
    """Small groups of names that might be one skill (union of linked pairs)."""
    items = sorted(names)
    parent = {n: n for n in items}

    def root(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n
    by_initial = {}
    for n in items:
        by_initial.setdefault(n[0], []).append(n)
    for a in items:
        candidates = by_initial.get(a[0], []) + [b for b in items if len(b) <= 6 and _acronym(b, a)]
        for b in candidates:
            if b == a or frozenset((a, b)) in rejected or not linked(a, b):
                continue
            parent[root(a)] = root(b)
    out = {}
    for n in items:
        out.setdefault(root(n), []).append(n)
    return [g for g in out.values() if 2 <= len(g) <= max_size]


def accepted_pairs(answer, group, index, rejected=frozenset()):
    """(variant, standard) pairs from the LLM's answer that are in the group and linked."""
    members = set(group)
    pairs = []
    for same in (answer or {}).get("same") or []:
        standard = index.canonical(same.get("standard") or "")
        if standard not in members:
            continue
        for v in same.get("variants") or []:
            v = index.canonical(v)
            if v in members and v != standard and frozenset((v, standard)) not in rejected and linked(v, standard):
                pairs.append((v, standard))
    return pairs


def run(conn, max_groups=300, dry_run=False, generate=None):
    index = skills.current(conn)
    rejected = {frozenset(r) for r in conn.execute("SELECT variant, canonical FROM skill_alias_rejections")}
    todo = groups(collect(conn, index), rejected)[:max_groups]
    stats = {"groups": len(todo), "asked": 0, "added": 0}
    now = datetime.now(timezone.utc).isoformat()
    for group in todo:
        try:
            answer = (generate or llm.generate)(PROMPT.format(names=json.dumps(group)), SCHEMA, timeout=120, task="jobs")
        except llm.Unavailable as exc:
            stats["stopped"] = str(exc)[:120]
            break
        except RuntimeError:
            continue
        stats["asked"] += 1
        for variant, standard in accepted_pairs(answer, group, index, rejected):
            stats["added"] += 1
            if not dry_run:
                conn.execute("INSERT OR IGNORE INTO skill_aliases (variant, canonical, source, created_at) VALUES (?, ?, 'llm', ?)",
                             (variant, standard, now))
    conn.commit()
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--max-groups", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    conn = db.get_connection()
    db.init_db(conn)
    if not llm.available():
        print("skill index: no LLM available (AI paused or unreachable); nothing done")
        return 0
    print(json.dumps(run(conn, args.max_groups, args.dry_run)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
