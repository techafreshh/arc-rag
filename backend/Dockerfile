FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "pydantic-ai[openrouter]" \
    fastapi \
    uvicorn \
    httpx \
    beautifulsoup4 \
    qdrant-client \
    python-dotenv \
    cachetools \
    langfuse

COPY backend/src/ /app/src/
COPY scripts/ /app/scripts/
COPY data/ /app/data/
RUN chmod +x /app/scripts/init.sh

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
