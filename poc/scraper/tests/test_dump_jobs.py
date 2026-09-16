import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dump_jobs import filter_and_cap, write_dump


ALL_JOBS = [
    {"id": "1", "title": "Senior Software Engineer", "companyName": "A"},
    {"id": "2", "title": "Data Analyst II", "companyName": "B"},
    {"id": "3", "title": "Warehouse Associate", "companyName": "C"},
    {"id": "4", "title": "Product Manager, Growth", "companyName": "D"},
    {"id": "5", "title": "software engineer intern", "companyName": "E"},
]


def test_filter_and_cap_matches_case_insensitively_and_tags_search_term():
    picked = filter_and_cap(ALL_JOBS, search_terms=["software engineer"], results_per_term=10)
    ids = {j["id"] for j in picked}
    assert ids == {"1", "5"}
    assert all(j["_search_term"] == "software engineer" for j in picked)


def test_filter_and_cap_respects_per_term_limit():
    picked = filter_and_cap(ALL_JOBS, search_terms=["software engineer"], results_per_term=1)
    assert len(picked) == 1


def test_filter_and_cap_unions_across_multiple_terms_without_duplicates():
    picked = filter_and_cap(ALL_JOBS, search_terms=["software engineer", "data analyst"], results_per_term=10)
    ids = [j["id"] for j in picked]
    assert set(ids) == {"1", "5", "2"}
    assert len(ids) == len(set(ids))  # no duplicate job objects even if matched by multiple terms


def test_filter_and_cap_excludes_non_matching_titles():
    picked = filter_and_cap(ALL_JOBS, search_terms=["software engineer"], results_per_term=10)
    ids = {j["id"] for j in picked}
    assert "3" not in ids  # Warehouse Associate
    assert "4" not in ids  # Product Manager


def test_write_dump_writes_timestamped_json_file(tmp_path):
    path = write_dump(ALL_JOBS[:2], dump_dir=str(tmp_path))
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["jobs"] == ALL_JOBS[:2]
    assert data["count"] == 2
