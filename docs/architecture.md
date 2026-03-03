# LegacyLens — RAG Architecture Document

## Vector Database Selection

**Choice:** Pinecone (managed cloud, free tier)

**Why Pinecone:**
- Zero infrastructure overhead — fully managed, no containers or VMs to maintain
- Free tier provides 1 index with 100K vectors, far exceeding our ~4,500 chunks
- Native metadata filtering on file path, language, chunk type, function name
- Cosine similarity search with consistent sub-500ms query latency
- Scales to production without migration — same API at any tier

**Tradeoffs considered:**
- **ChromaDB:** Simpler local development, zero setup, but requires self-hosting for deployment. No managed tier. Would need to run alongside the app on Fly.io, eating into the 512MB RAM budget.
- **Weaviate:** Supports hybrid search (BM25 + vector), which would help with exact identifier matching. But adds deployment complexity and learning curve. Overkill for demo scale.
- **pgvector:** Familiar SQL interface, but requires a managed Postgres instance. Adds cost and another service to manage.

**Verdict:** For a solo-dev, 24h MVP with demo-scale traffic, Pinecone's managed service eliminates an entire category of operational risk.

## Embedding Strategy

**Model:** Voyage `voyage-code-3` (1024 dimensions)

**Why Voyage Code-3:**
- Purpose-built for code retrieval — 13.8% higher accuracy than OpenAI text-embedding-3-large on code retrieval benchmarks (per Voyage AI's published results)
- 1024 dimensions (compact) — fits Pinecone free tier well, faster similarity search
- 32K token context window — can embed entire functions without truncation, vs OpenAI's 8K limit
- 200M free tokens — our entire codebase (~4M tokens) fits comfortably within free tier
- Supports `input_type` parameter — we use `"document"` for ingestion and `"query"` for search, which improves retrieval quality by ~5-10%

**Cost:** $0.00 (free tier, ~4M tokens embedded)

**Batch processing:** Voyage batches embedding calls internally via the LlamaIndex integration. We embed all chunks during a one-time ingestion script. No incremental updates needed for the demo.

## Chunking Approach

Three-tier strategy based on file language:

### Tier 1: C/Header Files — Tree-sitter AST Parsing
- Uses `tree-sitter` with `tree-sitter-c` language grammar
- Walks the AST root, extracts each `function_definition` as its own chunk
- Non-function top-level items (includes, structs, globals, typedefs) are grouped into `top_level` blocks
- Extracts function name from the `function_declarator → identifier` AST path
- Handles pointer return types (`int *func()`) via `pointer_declarator` traversal
- Line numbers come directly from AST node positions (exact)

### Tier 2: COBOL Files — Regex Boundary Detection
- COBOL's rigid columnar structure makes regex reliable
- Detects three boundary types:
  - **DIVISION** headers (`PROCEDURE DIVISION.`)
  - **SECTION** headers (`WORKING-STORAGE SECTION.`)
  - **PARAGRAPH** names (identifier at column 8-11 followed by period)
- Each boundary creates a chunk that spans from that boundary to the next
- Pre-boundary content captured as a `preamble` chunk

### Tier 3: Fallback — LlamaIndex SentenceSplitter
- For Yacc (`.y`), Lex (`.l`), `.def`, and other files
- Fixed-size splitting: 1500 chars per chunk, 200 char overlap
- Line numbers estimated from character offset matching

### Oversized Chunk Handling
- Any chunk exceeding 3000 characters is automatically re-split using the fallback splitter
- Original metadata (file path, language, function name) is preserved on sub-chunks
- Chunk type gets `_split` suffix for traceability

### Results
- **~4,500 total chunks** from the GnuCOBOL codebase
- **Breakdown:** ~3,800 C chunks (functions + top-level), ~200 COBOL chunks, ~500 fallback
- **Average chunk size:** ~400 tokens
- **Metadata per chunk:** `file_path`, `language`, `line_start`, `line_end`, `chunk_type`, `function_name`

## Retrieval Pipeline

### Query Flow

```
1. User submits query + mode selection
         │
2. Voyage Code-3 embeds query (input_type="query")     ~1-1.5s
         │
3. Pinecone cosine similarity search (top_k=5)          ~0.3-0.5s
         │
4. Source chunks returned to frontend via SSE            ← instant
         │
5. Context assembly: chunks formatted with metadata
   headers (file path, lines, language, function name)
         │
6. Mode-specific system prompt + context + query
   sent to xAI Grok LLM
         │
7. LLM streams response token-by-token via SSE          ~4-6s
```

### Two-Phase Architecture
The streaming endpoint (`/api/query/stream`) splits retrieval and generation:
- **Phase 1 (Retrieval):** Embed query → Pinecone search → return sources immediately as an SSE `sources` event. User sees relevant code within ~2 seconds.
- **Phase 2 (Generation):** Build context from retrieved nodes → stream LLM tokens one at a time as SSE `token` events. User sees the answer forming in real-time.

This architecture dramatically reduces perceived latency. Total end-to-end is ~6-8 seconds, but the user sees meaningful content at the ~2 second mark.

### Context Assembly
Retrieved chunks are formatted with metadata headers before being sent to the LLM:

```
### cobc/cobc.c:760-806
Language: c | Type: function | Function: cobc_abort
```<code>```
[chunk text]
```</code>```

This structured format helps the LLM cite sources accurately and distinguish between files/languages.

### Mode-Specific Prompting
All 8 modes share the same retrieval pipeline. The only difference is the system prompt sent to the LLM:
- Each mode has a specialized task description (explain, extract business logic, trace dependencies, etc.)
- A shared preamble enforces citation rules, honesty constraints, and formatting conventions
- The LLM receives: `[mode system prompt] + [formatted context] + [user query]`

## Failure Modes

### Low-relevance retrieval
**Symptom:** Top-5 chunks have low cosine similarity scores (<0.3).
**Observed:** Happens with very abstract queries ("how does the compiler work?") where no single chunk is a strong match.
**Mitigation:** The system prompt instructs the LLM to be honest when context is insufficient. Relevance scores are shown to the user for transparency.

### Identifier-exact matching
**Symptom:** Searching for an exact variable name (e.g., `cb_source_file`) sometimes misses the definition but finds usage sites.
**Root cause:** Semantic search optimizes for meaning similarity, not string matching. BM25/hybrid search would help here.
**Mitigation:** The Cross-Reference mode prompt specifically instructs the LLM to look for definitions vs. usage sites. Not a perfect fix — a hybrid search index would be the proper solution.

### Cross-file reasoning
**Symptom:** Questions about call chains that span 3+ files may only retrieve 1-2 relevant files in top-5.
**Root cause:** Top-k=5 limits how many files can be represented. Increasing top-k increases context but also noise.
**Mitigation:** The Dependency Mapping and Impact Analysis modes prompt the LLM to explicitly note when it needs additional files to complete the analysis.

### COBOL chunk boundaries
**Symptom:** Some COBOL test files have non-standard formatting that the regex patterns miss.
**Root cause:** The regex assumes standard COBOL column conventions. Test fixtures and sample programs sometimes use free-form COBOL.
**Mitigation:** Files that produce zero boundary matches fall back to single-file chunks. This means lower granularity but no data loss.

### LLM latency
**Symptom:** End-to-end latency is 6-8 seconds, above the 3-second target.
**Breakdown:** Voyage embedding ~1-1.5s, Pinecone search ~0.3-0.5s, LLM generation ~4-6s.
**Mitigation:** Streaming architecture reduces perceived latency to ~2s (sources visible immediately). The LLM generation step is the bottleneck and is inherently limited by the provider's inference speed.

## Performance Results

| Metric | Target | Actual |
|--------|--------|--------|
| Query latency (end-to-end) | <3s | ~6-8s (2s perceived with streaming) |
| Retrieval latency | — | ~1.5-2s (embed + search) |
| LLM generation | — | ~4-6s (streaming) |
| Codebase coverage | 100% files | 100% (all .c, .h, .cob, .cbl, .cpy, .y, .l) |
| Chunks indexed | — | ~4,500 |
| Ingestion time | <5 min | ~3 min |

### Test Query Results

| Query | Relevant chunks in top-5 | Notes |
|-------|--------------------------|-------|
| "Where is the main entry point?" | 4/5 | Correctly finds `main()` in `cobc/cobc.c` |
| "Explain what cobc_abort does" | 5/5 | Direct function-level match |
| "Find all file I/O operations" | 3/5 | Retrieves `fileio.c` functions; misses some scattered I/O in other modules |
| "Show me error handling patterns" | 4/5 | Finds error reporting functions and abort handlers |
| "What are the dependencies of codegen?" | 3/5 | Gets codegen.c includes and key functions; can't trace full call graph |
| "What functions modify current_program?" | 3/5 | Finds major mutation sites; semantic search misses some exact matches |

**Average precision@5: ~73%** — meets the >70% target from the assignment.
