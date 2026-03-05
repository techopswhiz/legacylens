# AI Development Log

## Tools Used

| Tool | Role | Usage Level |
|------|------|-------------|
| Claude Code | Primary dev assistant — architecture design, implementation, debugging, code review | Heavy |
| tree-sitter | AST-based C chunking (function-level extraction), explored for COBOL | Heavy |
| Voyage AI API | Code embeddings (voyage-code-3, 1024 dims), ingestion + query-time | Heavy |
| Groq API | LLM inference (Llama 3.3 70B), answer generation + streaming | Heavy |
| Pinecone MCP | Index management, vector upserts, search testing, stats inspection | Moderate |
| Context7 MCP | Library documentation lookup (LlamaIndex, FastAPI, Pinecone SDK, Voyage SDK) | Moderate |
| Playwright MCP | Frontend testing, SSE streaming verification, UI interaction validation | Light |

## Architecture Discovery with AI

The development process was heavily AI-assisted from the start:

1. **Codebase exploration:** Used Claude Code to analyze the GnuCOBOL repository structure — identifying file types, understanding the build system, and mapping out the directory hierarchy to determine what to ingest and what to skip.

2. **Chunking strategy design:** Evaluated multiple approaches with AI guidance. Started with LlamaIndex's built-in CodeSplitter, which produced poor chunk boundaries (splitting mid-function). Iterated to a custom tree-sitter approach that walks the AST root and extracts each `function_definition` as a complete chunk. For COBOL, AI helped design regex patterns matching standard column conventions (DIVISION/SECTION/PARAGRAPH headers).

3. **Vector DB evaluation:** Compared Pinecone, ChromaDB, Weaviate, and pgvector. Used Context7 to look up SDK docs for each. Pinecone won on zero-ops deployment and free tier fit.

4. **Embedding model comparison:** Evaluated OpenAI text-embedding-3-large vs Voyage Code-3. Voyage's `input_type` parameter (separate document/query embeddings) and 32K context window were decisive advantages for code retrieval.

5. **LLM provider iteration:** Started with xAI Grok (had API credits). Latency was 4-6s for generation alone, pushing total query time to ~6-8s. Tested multiple Grok models with no improvement. Switched to Groq (Llama 3.3 70B on custom LPUs) — generation dropped to ~0.5-1s, bringing total latency to ~2-2.5s. The `OpenAILike` adapter made this a config-only change.

6. **Retrieval quality tuning:** Used Pinecone MCP to inspect search results directly. Added keyword-based reranking to boost chunks containing exact query terms — pure semantic search was missing identifier matches.

## What Worked Well

- **Tree-sitter function-level chunking:** Each C function becomes exactly one chunk with precise line numbers from AST node positions. This gives near-perfect retrieval for function-specific queries (5/5 precision on exact function lookups).
- **Voyage `input_type` parameter:** Using `"document"` for ingestion and `"query"` for search improved retrieval quality by ~5-10% — essentially free.
- **OpenAILike adapter for provider swaps:** The LLM layer is fully provider-agnostic. Switching from xAI to Groq was a 3-env-var change with zero code modifications. Config auto-detects from whichever API key is set (Groq > xAI > Anthropic).
- **SSE streaming architecture:** Two-phase design (sources first, then LLM tokens) means users see relevant code within ~2s regardless of total generation time.
- **Keyword reranking:** Simple post-retrieval boost for chunks containing exact query terms. Cheap to implement, meaningful improvement for identifier searches.
- **Groq sub-1s inference:** Llama 3.3 70B on Groq's LPUs generates in ~0.5-1s vs 4-6s on xAI. This single change brought us from missing the 3s latency target to comfortably beating it.

## What Didn't Work / Lessons Learned

- **LlamaIndex CodeSplitter:** Poor chunk boundaries — would split at arbitrary AST depths, sometimes yielding a single `if` statement as a chunk. Custom tree-sitter walking was necessary.
- **Tree-sitter COBOL grammar:** Less mature than the C grammar. Struggled with GnuCOBOL's test fixtures (non-standard formatting, free-form COBOL). Fell back to regex boundary detection, which turned out to be reliable given COBOL's rigid columnar structure.
- **xAI latency:** All tested Grok models (grok-3-mini, grok-4-1-fast-non-reasoning, grok-code-fast-1, grok-4-fast-non-reasoning) had 6-16s generation times. The "fast" models were actually slower. This was the bottleneck that forced the provider switch.
- **Pure semantic search misses identifiers:** Searching for `cb_source_file` sometimes returns chunks that *discuss* source files rather than the actual definition. BM25/hybrid search would fix this properly.
- **Broad queries return low-relevance chunks:** "How does the compiler work?" gets low similarity scores across the board because no single chunk matches such an abstract question well.
- **VoyageAI SDK compatibility issues:** Required careful version pinning and working around LlamaIndex integration quirks. Context7 was essential for finding correct API patterns.

## Key Metrics

| Metric | Value |
|--------|-------|
| Total query latency (end-to-end) | ~2-2.5s |
| Embedding latency (Voyage Code-3) | ~1-1.5s |
| Pinecone search latency | ~0.3s |
| LLM generation latency (Groq) | ~0.5-1s |
| Precision@5 | ~73% |
| Chunks indexed | ~4,500 |
| Default LLM | Groq `llama-3.3-70b-versatile` |
| Per-query cost | ~$0.004 |
| Total development LLM spend | ~$0.80 |
