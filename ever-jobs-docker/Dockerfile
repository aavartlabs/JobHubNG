FROM node:20-slim
WORKDIR /app
COPY dist ./dist
COPY package.json .
COPY package-lock.json .
RUN npm install --production --legacy-peer-deps
EXPOSE 3001
CMD ["node", "dist/apps/api/main.js"]
