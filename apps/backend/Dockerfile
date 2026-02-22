# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy dependency files
COPY pyproject.toml uv.lock* README.md ./

# Install dependencies (torch resolves from CPU-only index via pyproject.toml)
RUN uv sync --no-dev --compile-bytecode

# Stage 2: Runner
FROM python:3.12-slim AS runner

WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY . .

# Clean up any remaining cache or unnecessary files
RUN find . -type d -name "__pycache__" -exec rm -rf {} +

CMD ["python", "-m", "app.temporal.worker"]