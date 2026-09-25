# EverJobs container

EverJobs is the external job-scraping service the pipeline's `scraper/ingest.py` calls. On
pi05 it runs from a prebuilt bundle (systemd unit `jobhub-everjobs`). Its bundle isn't in
this repo, so to build the container:

```bash
rsync -a pi05:jobhub-poc/everjobs-runtime/{dist,package.json,package-lock.json} poc/everjobs/runtime/
docker build -t jobhub-everjobs poc/everjobs
```

`runtime/` is git-ignored. Settings match pi05's unit: port 3001, in-memory store,
`DEFAULT_SITE_NAMES` (which job boards are swept, decided server-side).
