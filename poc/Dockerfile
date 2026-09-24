# Stage 1: build the TypeScript bundles and the Tailwind stylesheet (Node needed only at
# build time, not runtime)
FROM node:22-slim AS frontend-build
WORKDIR /src/jobhub_poc/webapp/frontend
COPY jobhub_poc/webapp/frontend/package.json jobhub_poc/webapp/frontend/package-lock.json* ./
RUN npm install
COPY jobhub_poc/webapp/frontend/ ./
# Tailwind generates only the classes it finds in the templates (src/styles.css @source).
COPY jobhub_poc/webapp/templates/ ../templates/
RUN npm run build
# npm run build writes ../static/{app.js,auth.js,app.css}, i.e. /src/jobhub_poc/webapp/static/

# Stage 2: the actual runtime image -- Python only, no Node
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY jobhub_poc ./jobhub_poc
COPY scripts ./scripts
COPY fixtures ./fixtures
COPY --from=frontend-build /src/jobhub_poc/webapp/static/app.js ./jobhub_poc/webapp/static/app.js
COPY --from=frontend-build /src/jobhub_poc/webapp/static/auth.js ./jobhub_poc/webapp/static/auth.js
COPY --from=frontend-build /src/jobhub_poc/webapp/static/app.css ./jobhub_poc/webapp/static/app.css
ENV WEB_PORT=3000
EXPOSE 3000
CMD ["python", "-m", "jobhub_poc.webapp.app"]
