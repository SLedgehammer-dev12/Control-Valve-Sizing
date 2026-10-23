FROM python:3.12-slim

ARG APP_VERSION=dev

LABEL org.opencontainers.image.title="Control Valve Sizing" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.source="https://github.com/SLedgehammer-dev12/Control-Valve-Sizing"

ENV APP_VERSION="${APP_VERSION}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/api/health')"

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8501", "--limit-concurrency", "20"]
