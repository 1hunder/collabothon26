FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependency layer (lock file optional)
COPY pyproject.toml uv.lock* ./
RUN if [ -f uv.lock ]; then uv sync --frozen --no-dev --no-install-project; \
    else uv sync --no-dev --no-install-project; fi

# Application (package incl. migrations and fixtures)
COPY alembic.ini ./
COPY financequest ./financequest
COPY start.sh ./start.sh
# a Windows checkout gives the script CRLF line endings, which make "exec /app/start.sh" fail
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh
RUN if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv sync --no-dev; fi

RUN mkdir -p /app/data && useradd --system --uid 10001 --no-create-home app && chown -R app /app
USER app

EXPOSE 8000
CMD ["/app/start.sh"]
