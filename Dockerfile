FROM python:3.11-slim

WORKDIR /app

# Non-root user creation
RUN useradd -m -u 1000 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY ARCHITECTURE.md SECURITY.md LIMITATIONS.md ./

ENV PYTHONPATH=/app/src
USER appuser

EXPOSE 8000
CMD ["uvicorn", "relay.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
