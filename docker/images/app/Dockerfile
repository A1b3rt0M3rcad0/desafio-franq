# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.14
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY packages ./packages

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && python -m pip install --no-deps \
        -e packages/core \
        -e packages/api \
        -e packages/runner \
        -e packages/ui \
    && mkdir -p /app/data

CMD ["python", "-m", "package.runner.main"]
