# LegacyLens

RAG-powered code exploration for legacy enterprise codebases.

**Live:** [https://legacylens.fly.dev](https://legacylens.fly.dev)

LegacyLens makes the [GnuCOBOL](https://github.com/OCamlPro/gnucobol) compiler — 200K+ lines of C, COBOL, Yacc, and Lex — queryable through natural language. Ask questions, get answers with cited source files and line numbers.

## Features

- **8 analysis modes:** Explain, Business Logic, Dependencies, Translate, Cross-Reference, Summarize, Impact Analysis, Documentation Generation
- **Streaming responses:** Sources appear instantly (~2s), LLM answer streams token-by-token
- **Syntax highlighting:** C and COBOL source snippets with Highlight.js
- **Syntax-aware chunking:** Tree-sitter for C (function-level), regex for COBOL (paragraph-level), fallback for Yacc/Lex
- **Retro UI:** Pixel fonts, scanlines, purple/green glow aesthetic

## Architecture

```
User Query
    │
    ▼
┌──────────────┐     ┌────────────────┐     ┌──────────────┐
│  FastAPI      │────▶│  Voyage Code-3  │────▶│  Pinecone    │
│  /api/query   │     │  Embedding      │     │  Top-K Search│
│  /stream      │     │  (1024 dims)    │     │  (cosine)    │
└──────────────┘     └────────────────┘     └──────┬───────┘
                                                    │
                                                    ▼
                                            ┌──────────────┐
                                            │  xAI Grok    │
                                            │  LLM Answer  │
                                            │  (streaming)  │
                                            └──────────────┘
```

| Component | Technology |
|-----------|-----------|
| Vector DB | Pinecone (managed, free tier) |
| Embeddings | Voyage `voyage-code-3` (1024 dims) |
| LLM | xAI Grok via OpenAI-compatible API |
| Framework | LlamaIndex |
| Backend | Python / FastAPI |
| Frontend | Single HTML file (no build step) |
| Chunking | Tree-sitter (C), regex (COBOL), SentenceSplitter (fallback) |
| Deployment | Fly.io |

## Setup

### Prerequisites

- Python 3.12+
- API keys for Pinecone, Voyage AI, and xAI (or Anthropic)

### Install

```bash
git clone https://github.com/techopswhiz/legacylens.git
cd legacylens
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Required environment variables:

| Variable | Purpose |
|----------|---------|
| `PINECONE_API_KEY` | Pinecone vector database access |
| `VOYAGE_API_KEY` | Voyage AI embedding model |
| `XAI_API_KEY` | xAI Grok LLM (or use `ANTHROPIC_API_KEY` for Claude) |
| `PINECONE_INDEX_NAME` | Index name (default: `legacylens`) |

### Ingest a Codebase

Download GnuCOBOL and run the ingestion pipeline:

```bash
python scripts/download_codebase.py
python scripts/ingest.py
```

This will:
1. Clone the GnuCOBOL repo into `codebase/gnucobol/`
2. Scan for `.c`, `.h`, `.cob`, `.cbl`, `.cpy`, `.y`, `.l` files
3. Chunk using syntax-aware splitting (tree-sitter for C, regex for COBOL)
4. Generate embeddings with Voyage Code-3
5. Upsert vectors into Pinecone

### Run Locally

```bash
uvicorn app.main:app --reload --port 8080
```

Open [http://localhost:8080](http://localhost:8080).

### Deploy to Fly.io

```bash
fly launch
fly secrets set PINECONE_API_KEY=... VOYAGE_API_KEY=... XAI_API_KEY=...
fly deploy
```

## Project Structure

```
legacylens/
├── app/
│   ├── main.py              # FastAPI routes, SSE streaming
│   ├── config.py             # Environment variable loading
│   ├── ingest/
│   │   ├── pipeline.py       # Ingestion orchestrator
│   │   ├── chunker.py        # Tree-sitter + regex chunking
│   │   └── loader.py         # File discovery and reading
│   ├── query/
│   │   ├── engine.py         # Pinecone retrieval + LLM streaming
│   │   └── prompts.py        # Mode-specific system prompts
│   └── static/
│       └── index.html        # Single-file retro frontend
├── scripts/
│   ├── ingest.py             # CLI: run ingestion
│   └── download_codebase.py  # CLI: clone GnuCOBOL
├── docs/
│   ├── assignment.md         # Project requirements
│   ├── pre-search.md         # Pre-search architecture decisions
│   ├── architecture.md       # RAG architecture documentation
│   └── costs.md              # AI cost analysis
├── Dockerfile
├── fly.toml
├── requirements.txt
└── .env.example
```

## API

### `POST /api/query/stream`

Server-Sent Events endpoint for streaming queries.

**Request:**
```json
{
  "query": "What does cobc_abort do?",
  "top_k": 5,
  "mode": "explain"
}
```

**Events:**
- `event: sources` — JSON array of source chunks (sent after retrieval, ~2s)
- `event: token` — Single LLM token string (repeated)
- `event: done` — `{"latency_ms": 6200}`
- `event: error` — `{"detail": "error message"}`

**Modes:** `explain`, `business_logic`, `dependencies`, `translate`, `xref`, `summarize`, `impact`, `docgen`

### `POST /api/query`

Non-streaming query endpoint. Returns full answer + sources in one response.

### `GET /api/health`

Health check. Returns `{"status": "ok", "engine_ready": true}`.

## Analysis Modes

| Mode | Description |
|------|-------------|
| **Explain** | Plain English explanation of what the code does |
| **Business Logic** | Extract validation rules, formulas, and domain logic |
| **Dependencies** | Trace function calls, data flow, and module coupling |
| **Translate** | Suggest modern language equivalents (Python, Rust, Go) |
| **Cross-Reference** | Find where identifiers are defined, used, and modified |
| **Summarize** | High-level overview of modules and architecture |
| **Impact Analysis** | Assess blast radius — what breaks if code changes |
| **Doc Gen** | Generate developer-facing documentation |

## License

MIT
