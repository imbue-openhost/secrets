FROM python:3.12-alpine

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8080

CMD ["uv", "run", "--no-dev", "hypercorn", "-b", "0.0.0.0:8080", "secrets_app.app:app"]
