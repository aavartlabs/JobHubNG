import pytest

from jobhub_poc.alerts.rules import Rule, rule_matches


def _job(title="Senior SRE", location="Bengaluru, KA, in", company="Razorpay",
         description="Kubernetes, Terraform, on-call.", is_remote=False):
    return {"title": title, "location": location, "company_name": company,
            "description": description, "is_remote": is_remote}


def test_or_within_a_filter_and_across_filters():
    rule = Rule(titles=("sre", "devops"), locations=("bangalore", "remote"))
    assert rule_matches(rule, _job())                                            # SRE + Bengaluru(alias)
    assert rule_matches(rule, _job(title="DevOps Engineer", location="Remote"))
    assert not rule_matches(rule, _job(location="Kolkata, WB, in"))              # location fails
    assert not rule_matches(rule, _job(title="Data Analyst"))                    # title fails


def test_empty_filters_are_ignored():
    assert rule_matches(Rule(companies=("razorpay",)), _job())


def test_a_rule_with_no_filters_matches_nothing():
    """The form requires at least one filter; a filterless rule must not mean 'everything'."""
    assert not rule_matches(Rule(), _job())


@pytest.mark.parametrize("term,title,expected", [
    ("java", "Java Developer", True),
    ("java", "JavaScript Developer", False),       # word boundary, not substring
    ("sre", "Senior SRE II", True),
    ("sre", "Treasurer", False),
    ("product manager", "Senior Product Manager, Growth", True),
    ("c++", "C++ Engineer", True),                 # terms ending in punctuation still work
    ("devops", "Dev-Ops Lead", False),
])
def test_titles_match_whole_words_case_insensitively(term, title, expected):
    assert rule_matches(Rule(titles=(term,)), _job(title=title)) is expected


@pytest.mark.parametrize("wanted,location", [
    ("bangalore", "Bengaluru, Karnataka, in"),
    ("bengaluru", "Bangalore, India"),
    ("gurgaon", "Gurugram, HR, in"),
    ("mumbai", "Bombay"),
    ("kolkata", "Calcutta, WB"),
    ("ncr", "Noida, UP, in"),
    ("delhi", "New Delhi, in"),
])
def test_location_aliases(wanted, location):
    assert rule_matches(Rule(locations=(wanted,)), _job(location=location))


def test_remote_as_a_location_also_matches_the_remote_flag():
    assert rule_matches(Rule(locations=("remote",)), _job(location="United States", is_remote=True))


def test_keywords_match_title_or_description():
    assert rule_matches(Rule(keywords=("terraform",)), _job())
    assert rule_matches(Rule(keywords=("sre",)), _job(description=None))
    assert not rule_matches(Rule(keywords=("golang",)), _job())


@pytest.mark.parametrize("mode,is_remote,location,expected", [
    ("remote", True, "Anywhere", True),
    ("remote", False, "Remote, US", True),        # flag unset but location says remote
    ("remote", False, "Pune", False),
    ("onsite", False, "Pune", True),
    ("onsite", True, "Pune", False),
])
def test_work_mode(mode, is_remote, location, expected):
    rule = Rule(titles=("sre",), work_mode=mode)
    assert rule_matches(rule, _job(is_remote=is_remote, location=location)) is expected


def test_companies_match_whole_words():
    assert rule_matches(Rule(companies=("razorpay",)), _job(company="Razorpay Software Pvt Ltd"))
    assert not rule_matches(Rule(companies=("pay",)), _job(company="Razorpay"))
