# Stage 1: build the TypeScript bundle (Node needed only at build time, not runtime)
FROM node:20-slim AS frontend-build
WORKDIR /src/jobhub_poc/webapp/frontend
COPY jobhub_poc/webapp/frontend/package.json jobhub_poc/webapp/frontend/package-lock.json* ./
RUN npm install
COPY jobhub_poc/webapp/frontend/ ./
RUN npm run build
# npm run build writes to ../static/app.js, i.e. /src/jobhub_poc/webapp/static/app.js

# Stage 2: the actual runtime image -- Python only, no Node
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY jobhub_poc ./jobhub_poc
COPY scripts ./scripts
COPY fixtures ./fixtures
COPY --from=frontend-build /src/jobhub_poc/webapp/static/app.js ./jobhub_poc/webapp/static/app.js
ENV WEB_PORT=3000
EXPOSE 3000
CMD ["python", "-m", "jobhub_poc.webapp.app"]
