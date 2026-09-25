"""Compare LLMs on JobsHub's three AI jobs, scored by the site's own honesty checks, before
choosing the model chains (AI_MODELS_WRITE / AI_MODELS_JOBS). Nothing is stored.

- tailor: every resume x job pair in bakeoff_fixtures.json (made-up people). How often the
  model tried to add something the resume doesn't say (caught and put back by
  tailoring.verify), how much useful rewording survived, and a recheck that nothing
  ungrounded is left (must be 0).
- parse: each fixture resume as plain text -> resume_parse.normalise. Invented skills,
  bullets not copied from the text, roles/bullets found vs expected.
- jobs: the fixture postings, plus --real-jobs N public postings from --jobs-db (never
  resume data). Skills the posting doesn't mention (dropped by job_requirements.normalise).

Resume tasks go through the same path as the site: provider data_collection=deny, and
models that train on prompts are refused.

    OPENROUTER_API_KEY=... .venv/bin/python scripts/ai_bakeoff.py \\
        --write-models openai/gpt-6-luna-pro,deepseek/deepseek-v4-flash \\
        --jobs-models direct:meta,openai/gpt-6-luna-pro \\
        --jobs-db data/jobhub.db --real-jobs 50 --out bakeoff.json
"""
import argparse
import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhub_poc import db, job_reading, job_requirements, resume_parse, tailoring  # noqa: E402
from jobhub_poc.ai import direct, openrouter  # noqa: E402
from jobhub_poc.webapp.job_text import plain_text  # noqa: E402

FIXTURES = Path(__file__).with_name("bakeoff_fixtures.json")


def resume_as_text(r):
    """A fixture resume as the plain text an uploaded file would give."""
    lines = [r["name"], r["headline"], r["location"], "", "Summary", r["summary"], "",
             "Skills", ", ".join(r["skills"]), "", "Experience"]
    for role in r["roles"]:
        lines += ["", f"{role['title']}, {role['company']}", f"{role['start']} - {role['end']}"]
        lines += [f"- {b['text']}" for b in role["bullets"]]
    lines += ["", "Education"] + r["education"]
    return "\n".join(lines)


def _call(model, prompt, schema, task):
    started = time.monotonic()
    try:
        if model.startswith("direct:"):  # a provider's own API (public job text only; no cost reported)
            answer, served = direct.ask(model.split(":", 1)[1], prompt, schema, timeout=300, task=task)
            usage = {}
        else:
            answer, served, usage = openrouter.ask(model, prompt, schema, task, timeout=300)
        return {"answer": answer, "served": served, "seconds": time.monotonic() - started,
                "cost": float(usage.get("cost") or 0), "error": None}
    except Exception as exc:  # noqa: BLE001 -- recorded per case; never includes the key
        return {"answer": None, "seconds": time.monotonic() - started, "cost": 0.0,
                "error": f"{type(exc).__name__}: {exc}"[:200]}


def tailor_case(model, resume, job):
    reqs = job["requirements"]
    run = _call(model, tailoring.prompt(resume, job, reqs), tailoring.SCHEMA, "write")
    if run["answer"] is None:
        return run
    raw = run.pop("answer")
    out = tailoring.verify(raw, resume, job, reqs)
    skills = reqs["required_skills"] + reqs["preferred_skills"]
    bullets = [b for r in out["roles"] for b in r["bullets"]]
    raw_note = tailoring._sentences(raw.get("cover_note"))
    kept_note = tailoring._sentences(out["cover_note"])
    everything = tailoring.resume_text(resume)
    # The recheck: anything ungrounded still in the final output (the gate should make it 0).
    leftover = sum(bool(tailoring.problems(b["text"], b["original"], skills)) for b in bullets if b["status"] == "reworded")
    if out["summary_status"] == "tailored":
        leftover += bool(tailoring.problems(out["summary"], everything, skills))
    note_source = f"{everything}\n{job['title']}\n{job['company']}"
    leftover += sum(bool(tailoring.problems(s, note_source, skills)) for s in kept_note)
    run.update(
        caught=sum(b["status"] == "put_back" for b in bullets)
        + (out["summary_status"] == "original" and bool(tailoring._norm(raw.get("summary"))))
        + (len(raw_note) - len(kept_note)),
        reworded=sum(b["status"] == "reworded" for b in bullets),
        summary_tailored=out["summary_status"] == "tailored",
        note_sentences=len(kept_note), leftover=leftover)
    return run


def parse_case(model, resume):
    text = resume_as_text(resume)
    run = _call(model, resume_parse.PROMPT + text, resume_parse.SCHEMA, "write")
    if run["answer"] is None:
        return run
    raw = run.pop("answer")
    norm = resume_parse.normalise(raw, text)
    proposed = {s.strip().lower() for s in raw.get("skills") or [] if isinstance(s, str) and s.strip()}
    bullets = [b for r in norm["roles"] for b in r["bullets"]]
    run.update(invented_skills=len(proposed) - len(norm["skills"]),
               unverified_bullets=sum(b["unverified"] for b in bullets),
               roles_found=f"{len(norm['roles'])}/{len(resume['roles'])}",
               bullets_found=f"{len(bullets)}/{sum(len(r['bullets']) for r in resume['roles'])}")
    return run


_JEV_DB = None


def jev_job_case(title, text):
    """model "jev": job_reading.read end to end -- the AI_MODELS_JOBS draft, then Jev's
    decisions, with a vocabulary that grows over the run (an in-memory database)."""
    global _JEV_DB
    if _JEV_DB is None:
        _JEV_DB = sqlite3.connect(":memory:")
        db.init_db(_JEV_DB)
    started = time.monotonic()
    try:
        data, label = job_reading.read(_JEV_DB, title, text)
    except Exception as exc:  # noqa: BLE001
        return {"seconds": time.monotonic() - started, "cost": 0.0, "error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"seconds": time.monotonic() - started, "cost": 0.0, "error": None, "served": label,
            "skills_kept": len(data["required_skills"]) + len(data["preferred_skills"]), "invented_skills": 0,
            "required": data["required_skills"], "preferred": data["preferred_skills"],
            "seniority": data["seniority"], "work_mode": data.get("work_mode"),
            "role_family": data.get("role_family"), "min_years": data["min_years"]}


def job_case(model, title, text):
    if model == "jev":
        return jev_job_case(title, text)
    run = _call(model, job_requirements.PROMPT.format(title=title, text=text), job_requirements.SCHEMA, "jobs")
    if run["answer"] is None:
        return run
    raw = run.pop("answer")
    norm = job_requirements.normalise(raw, f"{title}\n{text}")
    proposed = len({s.strip().lower() for s in (raw.get("required_skills") or []) + (raw.get("preferred_skills") or [])
                    if isinstance(s, str) and s.strip()})
    kept = len(norm["required_skills"]) + len(norm["preferred_skills"])
    run.update(skills_kept=kept, invented_skills=proposed - kept, seniority=norm["seniority"], min_years=norm["min_years"],
               required=norm["required_skills"], preferred=norm["preferred_skills"])
    return run


def real_jobs(db_path, n):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = conn.execute("SELECT title, description FROM jobs WHERE LENGTH(description) > 400 "
                        "ORDER BY RANDOM() LIMIT ?", (n,)).fetchall()
    conn.close()
    return [(t, plain_text(d)[:12000]) for t, d in rows]


def summarise(runs, sums=()):
    ok = [r for r in runs if not r.get("error")]
    secs = sorted(r["seconds"] for r in ok)
    out = {"cases": len(runs), "failed": len(runs) - len(ok),
           "p50_s": round(statistics.median(secs), 2) if secs else None,
           "p95_s": round(secs[min(len(secs) - 1, int(len(secs) * 0.95))], 2) if secs else None,
           "cost_usd": round(sum(r["cost"] for r in runs), 5)}
    for key in sums:
        out[key] = sum(r.get(key) or 0 for r in ok)
    out["errors"] = sorted({r["error"] for r in runs if r.get("error")})[:3]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write-models", default="", help="comma-separated; resume tasks (tailor, parse)")
    ap.add_argument("--jobs-models", default="", help="comma-separated; job-reading task")
    ap.add_argument("--jobs-db", help="a jobhub.db to draw real public postings from")
    ap.add_argument("--real-jobs", type=int, default=0)
    ap.add_argument("--out", help="write every case as JSON here")
    args = ap.parse_args(argv)
    fx = json.loads(FIXTURES.read_text())
    postings = [(j["title"], j["text"]) for j in fx["jobs"]]
    if args.jobs_db and args.real_jobs:
        postings += real_jobs(args.jobs_db, args.real_jobs)

    report, cases = {}, {}
    for model in [m for m in args.write_models.split(",") if m]:
        tail = [tailor_case(model, r, j) for r in fx["resumes"] for j in fx["jobs"]]
        parse = [parse_case(model, r) for r in fx["resumes"]]
        report[f"tailor  {model}"] = summarise(tail, ("caught", "reworded", "summary_tailored", "note_sentences", "leftover"))
        report[f"parse   {model}"] = summarise(parse, ("invented_skills", "unverified_bullets"))
        cases[model] = {"tailor": tail, "parse": parse}
        print(f"done {model} (write)", file=sys.stderr)
    for model in [m for m in args.jobs_models.split(",") if m]:
        jobs = [job_case(model, t, x) for t, x in postings]
        report[f"jobs    {model}"] = summarise(jobs, ("skills_kept", "invented_skills"))
        cases.setdefault(model, {})["jobs"] = jobs
        print(f"done {model} (jobs)", file=sys.stderr)

    for name, row in report.items():
        print(name)
        print("   ", json.dumps(row))
    if args.out:
        Path(args.out).write_text(json.dumps({"report": report, "cases": cases}, indent=1))
    return report


if __name__ == "__main__":
    main()
