# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir hatchling

COPY pyproject.toml .
RUN pip install --no-cache-dir --target /app/deps .

# Production stage
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/deps /app/deps
ENV PYTHONPATH=/app/deps

COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
