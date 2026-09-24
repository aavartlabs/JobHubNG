FROM node:22-slim
WORKDIR /app
# No npm dependencies: Node 22's fetch and http are all this needs.
COPY package.json ./
COPY src ./src
ENV NODE_ENV=production
ENV PORT=3300
EXPOSE 3300
USER node
CMD ["node", "src/server.js"]
