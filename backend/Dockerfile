FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY core core
COPY logic logic
COPY routers routers
COPY prompts prompts
COPY migrations migrations
COPY main.py models.py manage.py ./

RUN useradd --create-home --uid 10001 coach && mkdir -p /app/data && chown coach /app/data
USER coach
VOLUME /app/data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# One worker on purpose: background jobs and the per-athlete sync lock live in this process.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
