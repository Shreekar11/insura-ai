# Insura AI - Monorepo

A full-stack AI-powered insurance document processing system with FastAPI backend and Next.js frontend, orchestrated with Turborepo.

## 📁 Project Structure

```
insura-ai-monorepo/
├── apps/
│   ├── backend/       # FastAPI Python backend
│   └── frontend/      # Next.js TypeScript frontend
├── packages/          # Shared utilities
│   ├── shared-types/  # Shared TypeScript types
│   ├── ui/            # UI components
│   └── ...
├── turbo.json         # Turborepo configuration
├── package.json       # Root workspace
└── pnpm-workspace.yaml
```

## 🚀 Quick Start

### Prerequisites
- Node.js 18+
- pnpm 8.0+
- Python 3.11+
- Docker & Docker Compose

### Installation

```bash
# Install dependencies
pnpm install

# Copy environment variables
cp .env.example .env

# Start all services (requires Docker)
docker-compose up -d

# Run development servers
pnpm dev
```

**Access Points:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Turbo UI: http://localhost:3000

## 📦 Turborepo Features

- **Parallel execution**: All independent tasks run simultaneously
- **Caching**: Build artifacts are cached across runs
- **Task dependencies**: Respects `dependsOn` relationships

## 🐳 Docker Compose

See `docker-compose.yml` for all services (PostgreSQL, Neo4j, Temporal, Backend, Frontend).

```bash
# Start all services
docker-compose up -d
```
