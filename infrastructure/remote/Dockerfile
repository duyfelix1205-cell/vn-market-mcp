FROM python:3.11-slim
ARG PIP_EXTRA_INDEX_URL=https://vnstocks.com/api/simple
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url "${PIP_EXTRA_INDEX_URL}" -r requirements.txt
# Explicit copies keep .env files, Git history and unrelated host files out of the image.
COPY mcp_server/ mcp_server/
COPY pipeline/ pipeline/
COPY providers/ providers/
COPY quality/ quality/
COPY config/ config/
COPY db/ db/
COPY llm/ llm/
COPY schemas/ schemas/
COPY ops/ ops/
RUN useradd --uid 10001 --create-home appuser
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python", "-m", "mcp_server.http_server"]
