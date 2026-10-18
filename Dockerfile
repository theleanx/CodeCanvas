# Multi-stage build: frontend is built into static assets, then served by
# the same FastAPI process that runs the API. One image, one Render
# service, no cross-origin config to get right.

# --- Stage 1: build the frontend ---
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: backend + built frontend ---
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Render sets $PORT; default to 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
