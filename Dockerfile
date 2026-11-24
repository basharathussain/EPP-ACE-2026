# ---- stage 1: build the SPA (Node exists only here) ----
FROM node:22-alpine AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json* ./
RUN npm install
COPY ui/ .
RUN npm run build

# ---- stage 2: runtime, Python only ----
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DATA_DIR=/data UI_DIR=/app/ui/dist
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY eppace eppace
COPY server server
COPY --from=ui /ui/dist ui/dist
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
