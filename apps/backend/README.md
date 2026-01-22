# Insura AI

AI-powered workspace and assistant designed specifically for insurance operations.

## Installation

```bash
# Install dependencies
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys and database credentials
```

## Running the Server

```bash
# Start the server
uv run app/main.py

# Or with uvicorn
uvicorn app.main:app --reload
```

## Database Migration

The database auto-migrates on server startup. For manual migration:

```bash
# Check database connection
python scripts/migrate_db.py check

# Run migration
python scripts/migrate_db.py migrate

# Reset database (WARNING: deletes all data)
python scripts/migrate_db.py reset
```

## API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Configuration

Configure via environment variables in `.env`:

```env
# API Keys
MISTRAL_API_KEY=your_mistral_key
OPENROUTER_API_KEY=your_openrouter_key

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/insura_ai

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

## License

Proprietary
