FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
COPY data ./data
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --upgrade pip && pip install .

CMD ["sh", "-c", "alembic upgrade head && python -m app.cli.sync_theory && python -m app.main"]
