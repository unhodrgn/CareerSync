# Local demo only (docs/DECISIONS.md D7): runs the Vite dev server on :3000.
# Build context is the repo root (docker-compose.yml); VITE_API_TARGET is set by Compose.
FROM node:22-alpine
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
