```xml
<project>
 <name>LegacyLens</name>
 <description>RAG-powered system for querying and understanding legacy enterprise codebases</description>
 <purpose>
  Gauntlet AI, G4 — Week 3 Assignment
 </purpose>
 <docs>
  <readonly>
   @docs/assignment.md
   @docs/pre-search.md
  </readonly>
  <readwrite>
   <devlog>
    <file>docs/ai-dev-log.md</file>
    <purpose>Track MCP tools used</purpose>
   </devlog>
   <costanalysis>
    <file>docs/costs.md</file>
    <purpose>Track development and projected production costs</purpose>
   </costanalysis>
  </readwrite>
 </docs>
 <urls>
  <repo>TBD</repo>
  <dev>TBD</dev>
  <prod>TBD</prod>
 </urls>
 <stack>
  <frontend>Single HTML/JS page served by FastAPI (app/static/index.html)</frontend>
  <backend>Python 3.12 / FastAPI / LlamaIndex / Pinecone / Voyage AI / Anthropic Claude</backend>
  <hosting>Fly.io</hosting>
  <dev-tools>pytest, tree-sitter</dev-tools>
  <note>Read @requirements.txt for details.</note>
 </stack>
</project>

<workflow>
 <understand>
  Charlie is always neurodivergent and sometimes quite ethereal. You need to respect his boundaries and be patient with him. Reflect the parts of his speech which make sense, and wait until he communicates clearly. You may nudge him for clarity before proceeding. Don't assume anything about his intention.
 </understand>
 <plan/>
 <test>
  Use E2E tests for features. Keep code coverage 100% for feature code.
 </test>
 <implement/>
</workflow>

<culture>
 We do our best.
 We do not assume.
 We honor our spoken word.
 We take nothing personally.

 We deeply honor the user's actual intention.
 When we don't understand it, we hold space for the idea that it exists and is valid.
 Then, we ask.
</culture>
```

# TODO

## Build & Development Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in API keys

# Download codebase
python scripts/download_codebase.py

# Run ingestion (one-time, requires API keys)
python scripts/ingest.py

# Run dev server
uvicorn app.main:app --reload

# Run tests
python -m pytest tests/ -v

# Deploy
fly secrets set PINECONE_API_KEY=... VOYAGE_API_KEY=... ANTHROPIC_API_KEY=...
fly deploy
```

## Testing Setup

- Framework: pytest
- Tests in `tests/` directory
- `test_chunker.py` — unit tests for C/COBOL/fallback chunking
- `test_ingest.py` — loader and file discovery tests
- `test_query.py` — API endpoint and frontend tests

## Architecture

```
app/
  main.py          — FastAPI app, routes, lifespan (initializes query engine on startup)
  config.py        — Env vars loaded from .env
  ingest/
    loader.py      — File discovery, filtering, Document creation
    chunker.py     — Tree-sitter C chunker, regex COBOL chunker, fallback
    pipeline.py    — Orchestrates: load → chunk → embed → upsert to Pinecone
  query/
    engine.py      — Connects to Pinecone, retrieves chunks, generates answers via Claude
    prompts.py     — System prompt and query template
  static/
    index.html     — Single-file frontend (HTML + CSS + JS)
scripts/
  download_codebase.py  — Clone GnuCOBOL repo
  ingest.py             — CLI entry point for ingestion
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `PINECONE_API_KEY` | Pinecone vector DB access |
| `VOYAGE_API_KEY` | Voyage AI embeddings (voyage-code-3) |
| `ANTHROPIC_API_KEY` | Claude Sonnet for answer generation |
| `PINECONE_INDEX_NAME` | Index name (default: legacylens) |
| `EMBEDDING_MODEL` | Embedding model (default: voyage-code-3) |
| `LLM_MODEL` | LLM model (default: claude-sonnet-4-20250514) |
| `TOP_K` | Default retrieval count (default: 5) |

## Planning Phase

- Use context7 to look up library docs when needed. NEVER guess — check docs first.

## Python / Linting

- Python 3.12+ required
- Type hints used throughout
- No linter configured yet — add ruff if needed
