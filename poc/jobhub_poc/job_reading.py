"""Reading a job posting (public text) into what it asks for (job_requirements), with two
models doing what each is good at and code keeping them honest:

1. Muse (or the next model in AI_MODELS_JOBS) drafts a reading. job_requirements.normalise
   keeps only skills written in the posting.
2. Code adds known skills from skills_vocab that also appear in the posting.
3. Jev decides, in one request: how the posting treats each candidate (required / preferred /
   mentioned / absent), its seniority, work mode, employment type, role family and minimum
   years (only among numbers the posting states).
4. Skills Jev confirms as required or preferred join skills_vocab (job text only, never
   resumes), so the next posting's candidates don't depend on the draft alone.

Jev down: the draft is used as before. Every writing model down but Jev up: vocabulary
candidates only. Both down: llm.Unavailable, and the task waits."""
import json
import re
from datetime import datetime, timezone

from jobhub_poc import job_requirements
from jobhub_poc.ai import judgments, llm, typesafe

MAX_CANDIDATES = 40
MAX_STATE_CHARS = 30000  # Jev reads up to 32k tokens of state
_YEARS = re.compile(r"\b(\d{1,2})\s*(?:\+|(?:-|–|to)\s*\d+)?\s*(?:or more\s+|plus\s+)?(?:years?|yrs?)\b", re.I)
_EDGE = " \t.,;:()[]{}\"'“”‘’!?*|/\\"


def _key(skill):
    return re.sub(r"\s+", " ", (skill or "").lower()).strip(_EDGE)


def _grams(text, longest=4):
    words = [w.strip(_EDGE) for w in (text or "").lower().split()]
    words = [w for w in words if w]
    return {" ".join(words[i:i + n]) for n in range(1, longest + 1) for i in range(len(words) - n + 1)}


def vocab_hits(conn, text):
    """Known skills (skills_vocab) written in `text`, most-seen first."""
    grams = list(_grams(text))
    hits = []
    for start in range(0, len(grams), 500):
        chunk = grams[start:start + 500]
        marks = ",".join("?" * len(chunk))
        hits += conn.execute(f"SELECT display, seen FROM skills_vocab WHERE skill IN ({marks})", chunk).fetchall()
    return [d for d, _ in sorted(hits, key=lambda r: -r[1])]


def learn(conn, skills):
    now = datetime.now(timezone.utc).isoformat()
    for s in skills:
        k = _key(s)
        if k and len(k) <= 50 and len(k.split()) <= 5:
            conn.execute("INSERT INTO skills_vocab (skill, display, seen, added_at) VALUES (?, ?, 1, ?) "
                         "ON CONFLICT (skill) DO UPDATE SET seen = seen + 1", (k, s, now))
    conn.commit()


def seed_vocab(conn, complete=False):
    """First run: every skill already read from job postings (never from resumes), counted in
    memory and written in ONE transaction -- a commit per reading starved other connections
    (the worker died on "database is locked" on the Pi). complete=True adds whatever an
    interrupted seed missed, leaving existing rows (and their counts) as they are."""
    if not complete and conn.execute("SELECT 1 FROM skills_vocab LIMIT 1").fetchone():
        return
    counts, display = {}, {}
    for (data,) in conn.execute("SELECT data_json FROM job_requirements").fetchall():
        d = json.loads(data)
        for s in (d.get("required_skills") or []) + (d.get("preferred_skills") or []):
            k = _key(s)
            if k and len(k) <= 50 and len(k.split()) <= 5:
                counts[k] = counts.get(k, 0) + 1
                display.setdefault(k, s)
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany("INSERT INTO skills_vocab (skill, display, seen, added_at) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT (skill) DO NOTHING", [(k, display[k], n, now) for k, n in counts.items()])
    conn.commit()


def year_options(text):
    return sorted({int(n) for n in _YEARS.findall(text or "") if 0 < int(n) <= 30})


def read(conn, title, text):
    """(requirements, model label) for one posting."""
    haystack = f"{title}\n{text}"
    draft, draft_model, writers_down = None, None, False
    try:
        raw = llm.generate(job_requirements.PROMPT.format(title=title, text=text),
                           job_requirements.SCHEMA, timeout=300, task="jobs")
        draft, draft_model = job_requirements.normalise(raw, haystack), llm.model_name()
    except llm.Unavailable:
        writers_down = True
    except RuntimeError:
        pass  # a bad draft: Jev still reads the vocabulary candidates

    if not typesafe.available():
        if draft is None:
            raise llm.Unavailable("no model could read this job")
        return draft, draft_model

    seed_vocab(conn)
    candidates, seen = [], set()
    for s in (draft or {}).get("required_skills", []) + (draft or {}).get("preferred_skills", []) + vocab_hits(conn, haystack):
        if _key(s) not in seen and job_requirements.written_in(_key(s), haystack.lower()):
            seen.add(_key(s))
            candidates.append(s)
    candidates = candidates[:MAX_CANDIDATES]
    try:
        answers = typesafe.ask({"title": title, "posting": text[:MAX_STATE_CHARS]},
                               judgments.job_questions(candidates, year_options(haystack)))
    except typesafe.TypeSafeUnavailable:
        if draft is not None:
            return draft, draft_model
        raise
    data = judgments.read_job_answers(answers, candidates)
    if data["min_years"] and not job_requirements._says_years(haystack.lower(), data["min_years"]):
        data["min_years"] = None
    learn(conn, data["required_skills"] + data["preferred_skills"])
    label = "jev" + (f"+{draft_model}" if draft_model else "+vocab" if writers_down else "")
    return data, label
