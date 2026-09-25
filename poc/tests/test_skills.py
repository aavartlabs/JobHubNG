"""skills.py: one name per skill, and a match that understands variants."""
from jobhub_poc import skills
from jobhub_poc.matching import match

I = skills.SEED_INDEX


def test_variants_that_users_saw_as_different_are_the_same_skill():
    for a, b in [("Docker", "Dockers"), ("DevOps", "Devop"), ("IaC", "Infrastructure as Code"),
                 ("IAC", "Infrastructure as a code"), ("CI/CD", "CICD"), ("CI-CD", "ci cd"), ("Python 3", "python"),
                 ("Node.js", "NodeJS"), ("K8s", "Kubernetes"), ("Kubernetes", "Kuberentes")]:
        assert I.same(a, b), (a, b)


def test_look_alikes_stay_different():
    for a, b in [("Java", "JavaScript"), ("Go", "Git"), ("C", "C#"), ("React", "React Native"), ("SQL", "NoSQL")]:
        assert not I.same(a, b), (a, b)
    assert I.canonical("Kubernetes") == "kubernetes" and I.canonical("AWS") == "aws"  # not "plurals"
    assert skills.normalise("A/B testing") == "a b testing"


def test_table_aliases_join_the_seed(conn):
    conn.execute("INSERT INTO skill_aliases VALUES ('argo', 'argo cd', 'llm', '2026-09-26')")
    conn.commit()
    skills._cache["at"] = 0
    assert skills.current(conn).same("Argo", "Argo CD")


def test_the_match_credits_variants_and_says_what_the_user_wrote():
    resume = {"skills": ["Dockers", "IAC", "Devop"], "roles": [
        {"title": "SRE", "start": "2019", "end": "Present",
         "bullets": [{"text": "Ran k8s clusters with Terraform."}]}]}
    reqs = {"required_skills": ["Docker", "Infrastructure as Code", "DevOps", "Kubernetes"], "preferred_skills": [],
            "min_years": None, "seniority": "unknown"}
    result = match(resume, reqs, {"location": "", "is_remote": True})
    assert result["matched_required"] == ["Docker", "Infrastructure as Code", "DevOps", "Kubernetes"]
    assert result["missing_required"] == []
    assert result["wrote"] == {"Docker": "Dockers", "Infrastructure as Code": "IAC", "DevOps": "Devop", "Kubernetes": "k8s"}
