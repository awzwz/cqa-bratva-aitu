# One image for every role: SERVICE=api | worker | all (default). Frontend is served by the API as static files.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/cqa backend/cqa
RUN pip install -e ./backend
COPY frontend frontend
COPY results results
RUN useradd -m cqa && chown -R cqa /app
USER cqa
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD curl -fs http://127.0.0.1:8000/api/health || exit 1
ENV CQA_SERVICE=all CQA_DATA_DIR=/app/data
CMD ["sh", "-c", "if [ \"$CQA_SERVICE\" = worker ]; then python -m cqa.worker; else python -m uvicorn cqa.api.app:app --host 0.0.0.0 --port 8000 --workers 1; fi"]
