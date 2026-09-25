# EverJobs (the job scraper service) for an x86 host. Its prebuilt bundle is not in this repo:
# copy dist/ and package*.json from pi05's ~/jobhub-poc/everjobs-runtime into ./runtime first
# (README.md). Node 20 like pi05. better-sqlite3 has no prebuilt binary for it, so it's compiled
# in a build stage and only the result is copied into the runtime image.
FROM node:20-slim AS deps
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY runtime/package.json runtime/package-lock.json ./
RUN npm install --omit=dev --legacy-peer-deps --no-audit --no-fund --loglevel=error

FROM node:20-slim
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY runtime/package.json ./
COPY runtime/dist ./dist
ENV NODE_ENV=production PORT=3001 EVER_JOBS_STORE=memory \
    DEFAULT_SITE_NAMES=google,naukri,linkedin,indeed,glassdoor
EXPOSE 3001
USER node
CMD ["node", "dist/apps/api/main.js"]
