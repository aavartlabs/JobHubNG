import pytest

from jobhub_poc.resume_review import count, parse_month, review


@pytest.mark.parametrize("raw, expected", [
    ("2021", (2021, 1)), ("Mar 2021", (2021, 3)), ("march 2021", (2021, 3)), ("Sept. 2020", (2020, 9)),
    ("03/2021", (2021, 3)), ("2021-11", (2021, 11)), ("Present", "present"), ("till date", "present"),
    ("", None), (None, None), ("sometime", "bad"), ("13/2021", "bad"),
])
def test_parse_month(raw, expected):
    assert parse_month(raw) == expected


GOOD = {
    "name": "Asha Rao", "headline": "Senior SRE", "location": "Bengaluru, India",
    "summary": "Site reliability engineer with seven years running Kubernetes platforms for payments at scale.",
    "skills": ["Kubernetes", "Terraform", "AWS", "Python", "Prometheus"],
    "roles": [{"title": "SRE", "company": "Acme", "start": "Mar 2021", "end": "Present",
               "bullets": [{"id": "r1b1", "text": "Ran clusters.", "unverified": False}]}],
    "education": ["B.Tech, NIT"], "links": [],
}


def test_a_complete_resume_has_nothing_to_flag():
    assert review(GOOD) == {} and count(review(GOOD)) == 0


def test_gaps_are_flagged_with_suggestions_from_the_resume_itself():
    s = {**GOOD, "headline": "", "location": "", "summary": "SRE.", "skills": ["AWS"], "education": [],
         "roles": [{"title": "Platform Engineer", "company": "Acme", "start": "2023", "end": "2021",
                    "bullets": [{"id": "r1b1", "text": "Led a team of 50.", "unverified": True}]},
                   {"title": "", "company": "Beta", "start": "", "end": "whenever", "bullets": []}]}
    notes = review(s)
    headline = next(i for i in notes["basics"] if "headline" in i["message"])
    assert headline["fill"] == {"field": "headline", "value": "Platform Engineer"}  # already in the resume
    assert any("city" in i["message"] for i in notes["basics"])
    assert "very short" in notes["summary"][0]["message"]
    assert "Only 1 skill found" in notes["skills"][0]["message"]
    assert any("before the start" in i["message"] for i in notes["role-0"])
    assert any("Led a team of 50." in i["message"] for i in notes["role-0"])
    r1 = " ".join(i["message"] for i in notes["role-1"])
    assert "job title and the company" in r1 and "start and end dates" in r1 and "Mar 2021" in r1 and "bullet points" in r1
    assert "education" in notes


def test_empty_resume_says_what_to_add():
    notes = review({})
    assert {"basics", "summary", "skills", "experience", "education"} <= set(notes)
    assert all(i["level"] in ("fix", "check") for items in notes.values() for i in items)
