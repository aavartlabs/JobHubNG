"""Data-pipeline settings from config/pipeline.ini, shared by pi05 (warehouse ingest and
delta export) and pi09 (serving DB).

Standard library only: pi05 runs this with a minimal venv, so nothing here may import
Flask, dotenv, requests or jobhub_poc.config. Precedence: built-in defaults < the ini file
< env vars named JOBHUB_PIPELINE_<SECTION>_<KEY>. Unknown sections or keys are errors, so
a typo can't silently fall back to a default.
"""
import configparser
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_INI_PATH = Path(__file__).resolve().parent.parent / "config" / "pipeline.ini"
_ENV_PREFIX = "JOBHUB_PIPELINE_"

_DEFAULT_SEARCH_TERMS = (
    "engineer,product manager,data analyst,data scientist,designer,marketing,sales,"
    "customer success,operations,finance,human resources,devops,quality assurance,"
    "content,recruiter,manager,analyst,consultant,intern,director"
)

# section -> key -> (kind, default). kind: "days" / "count" are ints >= 0,
# "terms" is a non-empty list, "list" may be empty.
_SCHEMA = {
    "ingest": {"max_posted_age_days": ("days", "60")},
    "retention": {
        "warehouse_retention_days": ("days", "30"),
        "serving_retention_days": ("days", "15"),
        "keep_raw_dumps_days": ("days", "0"),
    },
    "serving": {
        "search_terms": ("terms", _DEFAULT_SEARCH_TERMS),
        "locations": ("list", ""),
        "results_per_term": ("count", "0"),
    },
    "sync": {"max_alert_terms": ("count", "200")},
    "archive": {"cold_after_days": ("days", "90")},
}


@dataclass(frozen=True)
class IngestConfig:
    max_posted_age_days: int  # 0 = no limit


@dataclass(frozen=True)
class RetentionConfig:
    warehouse_retention_days: int
    serving_retention_days: int
    keep_raw_dumps_days: int  # 0 = don't write raw dumps


@dataclass(frozen=True)
class ServingConfig:
    search_terms: tuple[str, ...]
    locations: tuple[str, ...]  # empty = any location
    results_per_term: int  # 0 = no cap


@dataclass(frozen=True)
class SyncConfig:
    max_alert_terms: int


@dataclass(frozen=True)
class ArchiveConfig:
    cold_after_days: int  # history older than this moves from the warehouse to MinIO


@dataclass(frozen=True)
class PipelineConfig:
    ingest: IngestConfig
    retention: RetentionConfig
    serving: ServingConfig
    sync: SyncConfig
    archive: ArchiveConfig


def _split(raw):
    seen = []
    for item in raw.replace("\n", ",").split(","):
        item = item.strip().lower()
        if item and item not in seen:
            seen.append(item)
    return tuple(seen)


def _parse(kind, raw, where):
    if kind in ("days", "count"):
        try:
            value = int(raw.strip())
        except ValueError:
            raise ValueError(f"{where} must be a whole number, got {raw!r}") from None
        if value < 0:
            raise ValueError(f"{where} must be 0 or more, got {value}")
        return value
    values = _split(raw)
    if kind == "terms" and not values:
        raise ValueError(f"{where} must list at least one term")
    return values


def load_pipeline_config(path=None, env=None):
    env = os.environ if env is None else env
    path = Path(path or env.get(f"{_ENV_PREFIX}INI") or DEFAULT_INI_PATH)
    if not path.is_file():
        raise FileNotFoundError(f"pipeline config not found: {path}")

    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path)
    for section in parser.sections():
        if section not in _SCHEMA:
            raise ValueError(f"{path}: unknown section [{section}]")
        for key in parser[section]:
            if key not in _SCHEMA[section]:
                raise ValueError(f"{path}: unknown key {key!r} in [{section}]")

    values = {}
    for section, keys in _SCHEMA.items():
        values[section] = {}
        for key, (kind, default) in keys.items():
            env_name = f"{_ENV_PREFIX}{section}_{key}".upper()
            if env_name in env:
                raw, where = env[env_name], env_name
            else:
                raw = parser.get(section, key, fallback=default)
                where = f"[{section}] {key}"
            values[section][key] = _parse(kind, raw, where)

    return PipelineConfig(
        ingest=IngestConfig(**values["ingest"]),
        retention=RetentionConfig(**values["retention"]),
        serving=ServingConfig(**values["serving"]),
        sync=SyncConfig(**values["sync"]),
        archive=ArchiveConfig(**values["archive"]),
    )
