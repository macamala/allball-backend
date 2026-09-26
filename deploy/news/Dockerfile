# Explicitly select this file ONLY for the existing News service. Not a root Dockerfile.
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt
# Allowlisted source only: no .git, .env, audit artifacts, test DBs, or score collector.
COPY *.py ./
COPY bot/ ./bot/
COPY sports_registry/ ./sports_registry/
COPY deploy/news/preflight.py ./deploy/news/preflight.py
RUN python deploy/news/preflight.py --check
USER 10001:10001
CMD ["python", "deploy/news/preflight.py", "--run"]
