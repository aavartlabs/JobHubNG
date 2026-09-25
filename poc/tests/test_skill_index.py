import json

import pytest

from jobhub_poc import skills
from jobhub_poc.ai import llm, skill_index


def _reading(conn, key, required, preferred=()):
    conn.execute("INSERT INTO job_requirements (job_dedupe_key, data_json, model, extracted_at) VALUES (?, ?, 'm', 'x')",
                 (key, json.dumps({"required_skills": list(required), "preferred_skills": list(preferred)})))
    conn.commit()


@pytest.fixture(autouse=True)
def fresh_index():
    skills.reset_cache()
    yield
    skills.reset_cache()


def test_linked_needs_a_textual_link():
    assert skill_index.linked("terraform cloud", "terraformcloud")
    assert skill_index.linked("argo cd", "argocd") and skill_index.linked("audits", "audit")
    assert skill_index.linked("automated test frameworks", "automated test framework")
    assert not skill_index.linked("java", "javascript")      # denylisted
    assert not skill_index.linked("scala", "scalar")          # denylisted
    assert not skill_index.linked("go", "git")
    assert not skill_index.linked("python", "pytorch")
    # Seen on prod data (gemma4:e2b said yes to all of these): a different ending is a different word...
    for a, b in [("azureml", "azure"), ("angularjs", "angular"), ("analytical", "analytics"),
                 ("orchestrator", "orchestration")]:
        assert not skill_index.linked(a, b), (a, b)
    # ...and acronyms are never merged by the batch (SSD is a drive; SCM is also source control).
    assert not skill_index.linked("ssd", "server side development")
    assert not skill_index.linked("ec", "ecs") and skill_index.linked("api", "apis")
    assert not skill_index.linked("gcp", "google cloud platform")


def test_a_typo_must_be_rare_next_to_the_spelling_it_is_a_typo_of():
    assert skill_index.linked("kuberentes", "kubernetes", {"kubernetes": 40, "kuberentes": 1})
    assert not skill_index.linked("kuberentes", "kubernetes")                       # no counts: no typo merges
    assert not skill_index.linked("ethercat", "ethernet", {"ethercat": 2, "ethernet": 3})  # both real words
    assert not skill_index.linked("data analytics", "data analysis", {"data analytics": 30, "data analysis": 25})
    assert not skill_index.linked("agents", "alerts", {"agents": 1, "alerts": 50})   # 2 letters in a short word


def test_groups_puts_variants_together_and_leaves_rejected_pairs_apart():
    names = {"terraform cloud": 3, "terraformcloud": 1, "python": 5, "gcp": 1, "google cloud platform": 1}
    found = sorted(sorted(g) for g in skill_index.groups(names))
    assert found == [["terraform cloud", "terraformcloud"]]
    rejected = {frozenset(("terraform cloud", "terraformcloud"))}
    assert skill_index.groups(names, rejected) == []


def test_accepted_pairs_keeps_only_linked_members_of_the_group():
    index = skills.Index()
    group = ["terraform cloud", "terraformcloud", "tfcloud"]
    answer = {"same": [{"standard": "Terraform Cloud", "variants": ["TerraformCloud", "tfcloud", "Ansible"]}]}
    assert skill_index.accepted_pairs(answer, group, index) == [("terraformcloud", "terraform cloud")]
    # The LLM naming a standard outside the group is ignored altogether.
    assert skill_index.accepted_pairs({"same": [{"standard": "hcl", "variants": ["tfcloud"]}]}, group, index) == []


def test_run_stores_llm_merges_and_the_index_uses_them(conn):
    _reading(conn, "a", ["Terraform Cloud", "Python"])
    _reading(conn, "b", ["TerraformCloud"], ["Pyhton scripting"])
    prompts = []

    def fake(prompt, schema, timeout, task):
        prompts.append(prompt)
        assert task == "jobs"
        return {"same": [{"standard": "terraform cloud", "variants": ["terraformcloud"]}]}

    stats = skill_index.run(conn, generate=fake)

    assert stats["added"] == 1 and stats["asked"] == len(prompts) >= 1
    row = conn.execute("SELECT variant, canonical, source FROM skill_aliases").fetchone()
    assert tuple(row) == ("terraformcloud", "terraform cloud", "llm")
    skills.reset_cache()
    assert skills.current(conn).same("TerraformCloud", "Terraform Cloud")


def test_run_rejects_denylisted_and_admin_rejected_merges(conn):
    _reading(conn, "a", ["Terraform Cloud", "TerraformCloud", "Scala", "Scalar"])
    conn.execute("INSERT INTO skill_alias_rejections VALUES ('terraformcloud', 'terraform cloud', 'x')")
    conn.commit()

    def says_all_same(prompt, schema, timeout, task):
        return {"same": [{"standard": "scala", "variants": ["scalar"]},
                         {"standard": "terraform cloud", "variants": ["terraformcloud"]}]}

    skill_index.run(conn, generate=says_all_same)
    assert conn.execute("SELECT COUNT(*) FROM skill_aliases").fetchone()[0] == 0


def test_run_stops_when_the_llm_is_unavailable_and_dry_run_writes_nothing(conn):
    _reading(conn, "a", ["Terraform Cloud", "TerraformCloud"])

    def paused(*a, **k):
        raise llm.Unavailable("AI is paused")

    assert "stopped" in skill_index.run(conn, generate=paused)
    stats = skill_index.run(conn, dry_run=True,
                            generate=lambda *a, **k: {"same": [{"standard": "terraform cloud", "variants": ["terraformcloud"]}]})
    assert stats["added"] == 1
    assert conn.execute("SELECT COUNT(*) FROM skill_aliases").fetchone()[0] == 0
