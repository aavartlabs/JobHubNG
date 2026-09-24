FROM node:24-slim
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev
COPY src ./src
ENV PORT=3100
EXPOSE 3100
CMD ["node", "src/server.js"]
