FROM node:24-bookworm-slim
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
EXPOSE 3000
# Vite proxies /api to backend using VITE_API_TARGET at runtime.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000", "--strictPort"]
