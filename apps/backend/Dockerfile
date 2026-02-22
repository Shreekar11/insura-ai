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
COPY apps/backend/pyproject.toml apps/backend/uv.lock* apps/backend/README.md ./

# Force CPU-only versions for heavy libraries to save space
# We use --index-url for torch to get the cpu version specifically
RUN uv venv && \
    uv pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    uv sync --no-dev --compile-bytecode

# Stage 2: Runner
FROM python:3.12-slim AS runner

WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY apps/backend/ ./

# Clean up any remaining cache or unnecessary files
RUN find . -type d -name "__pycache__" -exec rm -rf {} +

CMD ["python", "app/temporal/worker.py"]