FROM python:3.12-slim

WORKDIR /app

# Install system deps if needed
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy dependency files first
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --no-dev --compile-bytecode

# Copy source
COPY . .

CMD ["python", "app/temporal/worker.py"]