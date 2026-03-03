# LegacyLens — Pre-Search Document

## Phase 1: Define Your Constraints

### 1. Scale & Load Profile
- **Target codebase:** GnuCOBOL (open source COBOL compiler — mixed C/COBOL/Yacc, well over 10K LOC, 50+ files)
- **Source:** Listed in assignment as approved option
- **Expected query volume:** Demo scale initially (~5-20 users), but architecture should allow room to grow
- **Ingestion:** Batch (one-time ingest of full codebase)
- **Latency target:** <3 seconds end-to-end (per assignment)

### 2. Budget & Cost Ceiling
- Budget is not a constraint for this assignment
- Will track actual spend for the required cost analysis deliverable

### 3. Time to Ship
- **MVP deadline:** 24 hours (started ~2h late)
- **Final deadline:** Sunday 10:59 PM CT
- **MVP scope:** Exactly the assignment checklist — ingest, chunk, embed, store, search, query interface, snippets with file/line refs, basic answer generation, deployed
- **Nice-to-have for final:** 4+ code understanding features, polish, evaluation metrics

### 4. Data Sensitivity
- GnuCOBOL is open source (GPL/LGPL) — no restrictions on sending to external APIs
- No data residency requirements

### 5. Team & Skill Constraints
- Solo developer
- **RAG experience:** New to RAG (first build)
- **Python level:** Intermediate
- **COBOL familiarity:** Learning as needed
- **Implication:** Lean on frameworks with good docs and guardrails; avoid custom plumbing where a library exists

---

## Phase 2: Architecture Discovery

### 6. Vector Database Selection
- **Choice:** Pinecone (managed cloud)
- **Rationale:** Managed service = zero infra to deploy. Free tier provides 1 index, 100K vectors (far exceeds our ~5-10K chunks). Scales if we grow beyond demo.
- **Tradeoffs considered:** ChromaDB (simpler local dev, zero setup) vs Pinecone (managed, no self-hosting). Chose Pinecone for deployment simplicity and growth headroom.
- **Filtering:** Pinecone supports metadata filtering — we'll use this for file path, language type, chunk type queries.

### 7. Embedding Strategy
- **Choice:** Voyage `voyage-code-3`
- **Rationale:** Purpose-built for code retrieval. 13.8% better than OpenAI text-embedding-3-large on 32 code retrieval benchmarks. 1024 dimensions (compact). 32K token context window (vs OpenAI's 8K).
- **Cost:** 200M free tokens. Our codebase needs ~2-5M tokens. Effectively $0.
- **Dimension:** 1024 (default)
- **Batch processing:** Embed all chunks during ingestion; re-embed on code changes.

### 8. Chunking Approach
- **Choice:** Syntax-aware chunking from the start
- **C code (majority of GnuCOBOL):** Tree-sitter for C (mature, battle-tested) — chunk at function level
- **COBOL files:** Regex-based paragraph/section boundary detection (COBOL's rigid structure makes this feasible)
- **Fallback:** Fixed-size with overlap for files that fail to parse
- **Target chunk size:** 200-500 tokens per chunk
- **Metadata per chunk:** file_path, line_start, line_end, function/paragraph name, language, chunk_type
- **Overlap strategy:** Include parent scope context (e.g., file name + function signature) as prefix

### 9. Retrieval Pipeline
- **MVP:** Simple top-k similarity search (k=5)
- **Post-MVP (if time):** Re-ranking (Cohere rerank or similar), query expansion
- **Context assembly:** Combine top-k chunks with surrounding context for LLM
- **No multi-query or HyDE for MVP** — keep it simple

### 10. Answer Generation
- **MVP:** Claude Sonnet (via Anthropic API)
- **Rationale:** Top code understanding, 200K context window, clean Python SDK, already in ecosystem
- **Post-MVP:** Test against xAI Grok as alternative — keep LLM layer swappable via LlamaIndex abstraction
- **Design constraint:** All LLM calls go through LlamaIndex's LLM interface so providers can be swapped without code changes
- **Streaming:** Yes, for better UX in query interface

### 11. Framework Selection
- **Choice:** LlamaIndex
- **Rationale:** Purpose-built for RAG. Document → Node → Index → QueryEngine maps directly to our pipeline. ~15 lines to working prototype. First-class integrations with Pinecone, Voyage AI, and Anthropic.
- **Why not LangChain:** Broader scope means more concepts to learn. LlamaIndex is more focused for what we're building.
- **Why not custom:** 24h MVP timeline. Can't afford to build plumbing from scratch.

---

## Phase 3: Post-Stack Refinement

### 12. Failure Mode Analysis
- **No relevant results:** Return honest "no confident answer" response rather than hallucinating. Include the query and explain what was searched.
- **Ambiguous queries:** Return top-k results with relevance scores, let the user judge. Don't over-interpret.
- **Rate limiting:** Pinecone free tier has rate limits. Implement basic retry with backoff. Voyage API has rate limits — batch embedding calls.
- **Parse failures:** Syntax-aware chunking will fail on some files. Fall back to fixed-size chunking for unparseable files. Log which files failed and why.
- **Large files:** Some GnuCOBOL C files may be very large. Cap chunk count per file, prioritize function-level chunks.

### 13. Evaluation Strategy
- **Manual eval with assignment test queries** (6 scenarios from the assignment):
  1. "Where is the main entry point of this program?"
  2. "What functions modify the CUSTOMER-RECORD?" (adapted for GnuCOBOL's data structures)
  3. "Explain what [function X] does"
  4. "Find all file I/O operations"
  5. "What are the dependencies of [module X]?"
  6. "Show me error handling patterns in this codebase"
- **Metric:** Precision@5 — what % of top-5 results are relevant to the query
- **Target:** >70% relevant chunks in top-5 (per assignment)
- **Ground truth:** Build manually by reading GnuCOBOL source and identifying correct answers for each test query
- **Post-MVP:** Consider automated evaluation if time permits

### 14. Performance Optimization
- **Embedding cache:** Store embeddings in Pinecone; no need to re-embed unless code changes
- **Query preprocessing:** Basic normalization (lowercase, trim). No fancy query expansion for MVP.
- **Index optimization:** Pinecone handles this (managed service)
- **Target:** <3 seconds end-to-end per assignment requirements

### 15. Observability
- **Logging:** Python `logging` module. Log query text, retrieval latency, top-k scores, LLM response time.
- **Metrics to track:** Query latency (end-to-end), retrieval precision, embedding token usage, LLM token usage (for cost tracking)
- **MVP:** Basic structured logging to stdout. No fancy dashboards.
- **Post-MVP:** Consider adding request tracing if debugging retrieval issues

### 16. Deployment & DevOps
- **Hosting:** Fly.io (prior experience from Colaboard project). DigitalOcean as fallback.
- **Architecture:** Single FastAPI app serving both API endpoints and a simple frontend (HTML/JS served by FastAPI static files)
- **Secrets:** Environment variables on Fly.io for API keys (ANTHROPIC_API_KEY, VOYAGE_API_KEY, PINECONE_API_KEY)
- **CI/CD:** Manual deploy for MVP. `fly deploy` from local.
- **Ingestion:** Run ingestion as a one-time script before deploy. Pinecone persists data — no need to re-ingest on each deploy.

---

## Stack Summary

| Layer | Choice | Notes |
|-------|--------|-------|
| **Vector Database** | Pinecone (managed) | Free tier, 100K vectors, zero infra |
| **Embedding Model** | Voyage `voyage-code-3` | Code-optimized, 200M free tokens |
| **RAG Framework** | LlamaIndex | Purpose-built for RAG, Python-first |
| **LLM (MVP)** | Claude Sonnet (Anthropic) | Top code understanding, swappable |
| **LLM (test later)** | xAI Grok | Via LlamaIndex LLM abstraction |
| **Backend** | Python / FastAPI | Matches LlamaIndex ecosystem |
| **Frontend** | Simple HTML/JS (served by FastAPI) | Minimal — focus on functionality |
| **Chunking** | Tree-sitter (C) + regex (COBOL) | Syntax-aware from the start |
| **Deployment** | Fly.io | Prior experience, fallback to DigitalOcean |

## Estimated MVP Development Cost

| Component | Cost |
|-----------|------|
| Embeddings (Voyage code-3, ~5M tokens) | $0.00 (free tier) |
| LLM queries (~500 during dev, Claude Sonnet) | ~$7 |
| Vector DB (Pinecone free tier) | $0.00 |
| Fly.io hosting | $0.00 (free tier) |
| **Total** | **~$7** |
