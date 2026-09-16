"""Thin client for the EverJobs prebuilt API server.

Confirmed live against pi05 (2026-09-16): the query/results fields are NOT
honored server-side -- a site bucket like "google" or "indeed" returns every
job it has scraped for its ~1500-2000 registered companies regardless of the
query, and one call can take 2-3 minutes and return tens of MB. Callers
should therefore call search() once and filter/cap client-side (see
dump_jobs.py), not once per search term.
"""
import requests


class EverJobsError(Exception):
    pass


class EverJobsClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout_seconds: int = 180):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, results: int) -> list[dict]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            resp = requests.post(
                f"{self.base_url}/api/jobs/search",
                json={"input": {"query": query, "results": results}},
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.exceptions.RequestException as e:
            raise EverJobsError(f"request to EverJobs failed: {e}") from e

        if resp.status_code >= 300:
            raise EverJobsError(f"EverJobs returned HTTP {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        return data.get("jobs", [])
