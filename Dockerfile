FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY package ./package
COPY data ./data

RUN python -m pip install --upgrade pip \
    && python -m pip install .

CMD ["python", "-m", "package.runner.main"]
