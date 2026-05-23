# OpenDraft API

FastAPI service that wires the Next.js web UI to the engine pipeline.

## Dev
    cd api
    python -m venv .venv && source .venv/bin/activate
    pip install -e ".[dev]"
    uvicorn app.main:app --reload --port 7100

## Test
    pytest
