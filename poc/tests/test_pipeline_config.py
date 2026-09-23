from pathlib import Path

import pytest

from jobhub_poc.pipeline_config import DEFAULT_INI_PATH, load_pipeline_config


def _write(tmp_path, text):
    path = tmp_path / "pipeline.ini"
    path.write_text(text)
    return path


def test_checked_in_ini_loads_with_the_agreed_defaults():
    cfg = load_pipeline_config(DEFAULT_INI_PATH, env={})
    assert cfg.ingest.max_posted_age_days == 60
    assert cfg.retention.warehouse_retention_days == 30
    assert cfg.retention.serving_retention_days == 15
    assert cfg.retention.keep_raw_dumps_days == 0
    assert "engineer" in cfg.serving.search_terms
    assert cfg.serving.locations == ()
    assert cfg.archive.cold_after_days == 90


def test_missing_keys_fall_back_to_built_in_defaults(tmp_path):
    cfg = load_pipeline_config(_write(tmp_path, "[ingest]\n"), env={})
    assert cfg.ingest.max_posted_age_days == 60
    assert cfg.retention.serving_retention_days == 15
    assert cfg.serving.search_terms  # a non-empty built-in list


def test_file_values_are_read_and_lists_are_split_trimmed_and_deduped(tmp_path):
    cfg = load_pipeline_config(_write(tmp_path, """
[ingest]
max_posted_age_days = 45
[serving]
search_terms = SRE,  devops , sre ,, CloudOps
locations = Bengaluru, Remote
results_per_term = 25
"""), env={})
    assert cfg.ingest.max_posted_age_days == 45
    assert cfg.serving.search_terms == ("sre", "devops", "cloudops")
    assert cfg.serving.locations == ("bengaluru", "remote")
    assert cfg.serving.results_per_term == 25


def test_env_overrides_win_over_the_file(tmp_path):
    path = _write(tmp_path, "[retention]\nserving_retention_days = 15\n")
    cfg = load_pipeline_config(path, env={
        "JOBHUB_PIPELINE_RETENTION_SERVING_RETENTION_DAYS": "7",
        "JOBHUB_PIPELINE_SERVING_SEARCH_TERMS": "sre,devops",
    })
    assert cfg.retention.serving_retention_days == 7
    assert cfg.serving.search_terms == ("sre", "devops")


def test_ini_path_can_come_from_the_environment(tmp_path):
    path = _write(tmp_path, "[ingest]\nmax_posted_age_days = 5\n")
    cfg = load_pipeline_config(env={"JOBHUB_PIPELINE_INI": str(path)})
    assert cfg.ingest.max_posted_age_days == 5


@pytest.mark.parametrize("text,needle", [
    ("[ingest]\nmax_posted_age_days = soon\n", "max_posted_age_days"),
    ("[ingest]\nmax_posted_age_days = -1\n", "max_posted_age_days"),
    ("[ingest]\nmax_posted_age_dayz = 3\n", "max_posted_age_dayz"),   # typo'd key
    ("[injest]\n", "injest"),                                         # typo'd section
    ("[serving]\nsearch_terms = ,\n", "search_terms"),                # empty list
])
def test_invalid_config_fails_loudly_naming_the_problem(tmp_path, text, needle):
    with pytest.raises(ValueError, match=needle):
        load_pipeline_config(_write(tmp_path, text), env={})


def test_invalid_env_override_fails_loudly(tmp_path):
    with pytest.raises(ValueError, match="MAX_POSTED_AGE_DAYS"):
        load_pipeline_config(_write(tmp_path, ""), env={"JOBHUB_PIPELINE_INGEST_MAX_POSTED_AGE_DAYS": "x"})


def test_missing_file_is_an_error_not_silent_defaults(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_pipeline_config(tmp_path / "nope.ini", env={})


def test_zero_max_age_means_no_age_limit(tmp_path):
    cfg = load_pipeline_config(_write(tmp_path, "[ingest]\nmax_posted_age_days = 0\n"), env={})
    assert cfg.ingest.max_posted_age_days == 0


def test_module_imports_nothing_outside_the_stdlib():
    """pi05 runs the warehouse with a minimal venv (no Flask, no dotenv)."""
    source = Path(__file__).resolve().parent.parent / "jobhub_poc" / "pipeline_config.py"
    imports = [line.split()[1] for line in source.read_text().splitlines()
               if line.startswith(("import ", "from "))]
    assert not [m for m in imports if m.split(".")[0] in {"flask", "dotenv", "requests", "jobhub_poc"}]
