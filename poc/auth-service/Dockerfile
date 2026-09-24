# node:24-slim (the current Node LTS) -- better-sqlite3 13.0.3 declares engines.node >=22.
FROM node:24-slim
WORKDIR /app
COPY package.json package-lock.json* ./
# --ignore-scripts: better-sqlite3 ships a prebuilt binary for linux-x64 and
# linux-arm64 (node_modules/better-sqlite3/prebuilds/*.node) that it loads
# directly at require() time, but npm's default auto-behavior for a package
# with a binding.gyp (which better-sqlite3 has) is to still run
# `node-gyp rebuild` on install regardless -- and node:24-slim has no
# python3/build toolchain for that to succeed. Skipping install scripts
# avoids the unnecessary compile and uses the bundled prebuild instead.
# Confirmed by building this image without the flag first: npm install fails
# with "Could not find any Python installation to use".
RUN npm install --omit=dev --ignore-scripts
# Better Auth's migrate CLI is a separate package from better-auth itself and
# is deliberately not a project dependency (package.json only declares
# better-auth, better-sqlite3, resend). Baked into the image here (not
# fetched via `npx` at container boot) so `docker run` doesn't need network
# access just to apply schema migrations on startup. Pinned to the version
# confirmed working against this service's better-auth 1.7.5 config during
# this task's manual verification -- confirm it still applies cleanly if
# better-auth is ever bumped.
RUN npm install --no-save --ignore-scripts @better-auth/cli@1.4.21
COPY src ./src
# Better Auth reads NODE_ENV in several places; the one that matters here is
# that it refuses to start with an unset BETTER_AUTH_SECRET in production
# (a guard worth having) and stops leaking framework error pages. Rate
# limiting does NOT depend on this -- src/auth.js enables it explicitly --
# but leaving NODE_ENV unset in a deployed container is wrong regardless.
# Safe for cookie naming: with BETTER_AUTH_URL set (required, see
# .env.example), the __Secure- prefix follows that URL's scheme, not
# NODE_ENV.
ENV NODE_ENV=production
ENV PORT=3200
EXPOSE 3200
CMD ["sh", "-c", "node_modules/.bin/better-auth migrate --yes && node src/server.js"]
