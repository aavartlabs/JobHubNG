"""One name per skill, so "Dockers", "docker" and "Docker" match, and so do "IaC" and
"Infrastructure as Code". Used wherever a job's skills are compared with a resume's
(matching.py).

Three layers, cheapest first:
1. normalise(): case, spacing, equivalent punctuation (CI/CD = CI-CD = CICD), version tails
   ("Python 3"), and a trailing plural when the singular is a known skill ("Dockers").
2. Aliases: SEED below (curated) plus skill_aliases rows (added in batches by
   ai/skill_index.py and reviewable at /admin/skills). variant -> canonical.
3. A one-edit typo against known skills, for names of 6+ characters ("Kuberentes"), never
   for short ones (Go vs Git).

Index objects are immutable; current(conn) caches one per process for a few minutes."""
import re
import time

# variant -> canonical (all normalised). Curated; the LLM batch adds more in the table.
SEED = {
    "k8s": "kubernetes", "kube": "kubernetes", "golang": "go", "js": "javascript", "ts": "typescript",
    "postgres": "postgresql", "psql": "postgresql", "mongo": "mongodb", "gcp": "google cloud",
    "google cloud platform": "google cloud", "amazon web services": "aws", "azure cloud": "azure",
    "microsoft azure": "azure", "ms excel": "excel", "microsoft excel": "excel", "ml": "machine learning",
    "ai": "artificial intelligence", "dl": "deep learning", "nlp": "natural language processing",
    "cicd": "ci cd", "ci cd pipelines": "ci cd", "continuous integration": "ci cd", "node": "nodejs",
    "react js": "react", "reactjs": "react", "vue js": "vue", "vuejs": "vue", "angular js": "angularjs",
    "iac": "infrastructure as code", "devop": "devops", "dev ops": "devops", "sre": "site reliability engineering",
    "site reliability": "site reliability engineering", "tf": "terraform", "hashicorp terraform": "terraform",
    "gh actions": "github actions", "k8": "kubernetes", "elk": "elk stack", "elastic search": "elasticsearch",
    "rest api": "rest", "restful": "rest", "restful apis": "rest", "rest apis": "rest", "oop": "object oriented programming",
    "oops": "object oriented programming", "dsa": "data structures and algorithms", "sql server": "microsoft sql server",
    "mssql": "microsoft sql server", "ms sql": "microsoft sql server", "pyspark": "apache spark", "spark": "apache spark",
    "kafka": "apache kafka", "airflow": "apache airflow", "hadoop": "apache hadoop", "powerbi": "power bi",
    "ms power bi": "power bi", "gen ai": "generative ai", "genai": "generative ai", "llms": "large language models",
    "llm": "large language models", "qa": "quality assurance", "ux": "user experience", "ui": "user interface",
    "pm": "product management", "bi": "business intelligence", "etl pipelines": "etl", "sap abap": "abap",
    "salesforce crm": "salesforce", "sfdc": "salesforce", "cyber security": "cybersecurity", "infosec": "information security",
    "linux administration": "linux", "unix linux": "linux", "shell scripting": "bash", "bash scripting": "bash",
    "docker compose": "docker", "containers": "containerization", "helm charts": "helm", "prometheus grafana": "prometheus",
    "aws cloud": "aws", "ec2": "aws ec2", "s3": "aws s3", "c sharp": "c#", "csharp": "c#", "dotnet": ".net", "dot net": ".net",
    "asp net": "asp.net", "cpp": "c++", "c plus plus": "c++", "objective c": "objective-c", "nextjs": "next.js",
    "next js": "next.js", "node js": "nodejs", "springboot": "spring boot", "spring framework": "spring",
    "ms office": "microsoft office", "gitlab ci": "gitlab ci cd", "jenkins pipelines": "jenkins", "agile scrum": "scrum",
    "scrum master": "scrum", "pmp certification": "pmp", "project management professional": "pmp",
}
# Never the same skill, however alike they look (checked by the batch and the typo layer).
DIFFERENT = {frozenset(p) for p in [
    ("java", "javascript"), ("c", "c#"), ("c", "c++"), ("c#", "c++"), ("react", "react native"), ("sql", "nosql"),
    ("go", "git"), ("r", "rust"), ("scala", "scalar"), ("vue", "vuex"), ("swift", "swiftui"), ("perl", "pearl"),
]}
# Words that end in "s" but aren't plurals.
_NOT_PLURAL = {"kubernetes", "aws", "analytics", "devops", "jenkins", "sass", "less", "redis", "ios", "macos",
               "windows", "nodejs", "business", "statistics", "economics", "logistics", "ads", "cms", "dns",
               "gis", "hris", "sales", "operations", "css", "js", "ts", "express", "access", "process", "sas"}
_VERSION = re.compile(r"\s+v?\d+(\.\d+)*(\s*\+)?$")


def normalise(skill):
    """Lower case; punctuation that doesn't change meaning dropped; no version tail."""
    s = (skill or "").lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"(?<=\w)[./](?=js\b)", "", s)          # node.js / vue.js -> nodejs / vuejs
    s = re.sub(r"[/\-_,;:()\[\]'\"]+", " ", s)          # ci/cd, ci-cd -> ci cd
    s = re.sub(r"\s+", " ", s).strip(" .")
    s = _VERSION.sub("", s)
    words = s.split()
    if len(words) >= 3:  # "infrastructure as a code" = "infrastructure as code"; "a b testing" keeps its "a"
        s = " ".join([words[0]] + [w for w in words[1:] if w not in ("a", "an", "the")])
    return s


class Index:
    """variant -> canonical, plus the set of canonical skills for typo matching."""

    def __init__(self, aliases=None):
        self.aliases = {normalise(k): normalise(v) for k, v in {**SEED, **(aliases or {})}.items()}
        self.known = set(self.aliases.values())

    def canonical(self, skill):
        s = normalise(skill)
        if not s:
            return ""
        if s in self.aliases:
            return self.aliases[s]
        if s.endswith("s") and s not in _NOT_PLURAL and len(s) > 3:
            single = s[:-1]
            if single in self.known or single in self.aliases:
                return self.aliases.get(single, single)
        return s

    def same(self, a, b):
        """Same skill? Alias/normalise first, then a one-edit typo for long names."""
        ca, cb = self.canonical(a), self.canonical(b)
        if not ca or not cb:
            return False
        if ca == cb:
            return True
        if frozenset((ca, cb)) in DIFFERENT or min(len(ca), len(cb)) < 6:
            return False
        return _one_edit(ca, cb)

    def learn(self, known_skills):
        """Add skills seen in the data (job readings) as typo targets."""
        self.known.update(self.canonical(s) for s in known_skills if s)
        return self


def _one_edit(a, b):
    """True if a and b differ by one insertion, deletion, substitution or adjacent swap."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1
                                   and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


SEED_INDEX = Index()
_cache = {"at": 0.0, "index": SEED_INDEX}
CACHE_SECONDS = 600


def current(conn):
    """SEED plus the skill_aliases table, cached for CACHE_SECONDS."""
    if time.monotonic() - _cache["at"] < CACHE_SECONDS:
        return _cache["index"]
    try:
        rows = conn.execute("SELECT variant, canonical FROM skill_aliases").fetchall()
    except Exception:  # noqa: BLE001 -- table not created yet: the seed alone
        rows = []
    _cache.update(at=time.monotonic(), index=Index({r[0]: r[1] for r in rows}))
    return _cache["index"]
