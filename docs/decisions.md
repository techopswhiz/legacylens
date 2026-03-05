# LegacyLens — Decisions, Tradeoffs & Edge Cases

Quick-reference document for interviews. Organized by topic so you can jump to whatever they ask about.

---

## 1. Vector Database: Why Pinecone?

**Decision:** Pinecone (managed cloud, free tier)

**Why not the others:**
- **ChromaDB** — Simplest to prototype with (embedded, no server). But it's in-process — you have to run it alongside your app. On Fly.io with 512MB RAM, that's a problem. No managed cloud offering means I'd own the uptime.
- **Weaviate** — Has hybrid search (BM25 + vector), which would've helped with exact identifier matching (a known weakness of pure semantic search). But it's a full server to deploy and manage. Overkill for demo scale. If I were building this for production, Weaviate would be my pick.
- **Qdrant** — Good filtering, Rust-based performance. But similar deployment story to Weaviate. No compelling advantage over Pinecone for this use case.
- **pgvector** — Familiar SQL interface, could've used Supabase. But it's a general-purpose extension, not optimized for ANN search at scale. Also means managing a Postgres instance.

**What I'd change for production:** Switch to Weaviate or Qdrant for hybrid search. Pure semantic search misses exact identifier matches — when someone searches for `cb_source_file`, BM25 would find exact string matches that cosine similarity sometimes misses.

---

## 2. Embeddings: Why Voyage Code-3?

**Decision:** Voyage `voyage-code-3` (1024 dimensions)

**The case for Voyage over OpenAI:**
- 13.8% better on code retrieval benchmarks (Voyage's published numbers, not mine — but consistent with what I observed)
- 32K token context window vs OpenAI's 8K. GnuCOBOL has functions that are 500+ lines — with OpenAI, those would get truncated during embedding. Voyage handles them fine.
- 1024 dimensions vs OpenAI's 1536/3072. Smaller vectors = faster search, less storage, and in practice I saw no quality difference.
- 200M free tokens. Our entire codebase is ~4M tokens. Essentially free.

**Tradeoff:** Voyage is a smaller company than OpenAI. If they went down or deprecated the model, I'd need to re-embed everything. Mitigation: the ingestion pipeline takes ~3 minutes, so re-embedding is cheap.

**The `input_type` parameter:** Voyage supports separate `"document"` and `"query"` input types. Documents get embedded differently from queries. This is a 5-10% retrieval quality boost for free — you just pass the right flag.

---

## 3. Chunking: Why Tree-sitter + Regex?

**Decision:** Three-tier strategy — Tree-sitter AST parsing for C, regex for COBOL, LlamaIndex SentenceSplitter fallback.

### Why not just fixed-size chunks?
Fixed-size chunks split mid-function. A 1500-char window might cut a function in half, losing semantic coherence. When the user asks "What does cobc_abort do?", you want the entire function as one chunk, not two halves with 200 chars of overlap.

### Why not LlamaIndex's built-in CodeSplitter?
I tried it first. It uses tree-sitter under the hood but with less control over what constitutes a "chunk." It would split at arbitrary AST depths, sometimes giving you a single `if` statement as a chunk. My custom approach walks only the top level of the AST: each `function_definition` = one chunk, everything else (includes, structs, globals) grouped into `top_level` blocks.

### Why regex for COBOL instead of tree-sitter?
Tree-sitter has a COBOL grammar, but it's less mature than the C grammar and struggled with GnuCOBOL's test fixtures (non-standard formatting, free-form COBOL mixed with fixed-format). COBOL's rigid columnar structure makes regex reliable for boundary detection: `DIVISION`, `SECTION`, and `PARAGRAPH` headers follow predictable patterns.

### Edge cases handled:
- **Oversized chunks (>3000 chars):** Auto-split using SentenceSplitter. Original metadata preserved, chunk_type gets `_split` suffix.
- **Files that fail to parse:** Entire file becomes one chunk (chunk_type: `file_fallback`). No data loss, just lower granularity.
- **Encoding issues:** UTF-8 with `errors="replace"` fallback. Binary files filtered out by the loader.
- **Empty files / generated files:** Filtered during file discovery (skip files <10 bytes, skip `autom4te.cache/`, `*.o`, etc.)

### What I'd do differently:
- **Include parent context as a prefix.** Right now each chunk stands alone. Better: prepend `// File: cobc/cobc.c | Function: cobc_abort` as a text prefix to every chunk. This helps the embedding model understand context without relying on metadata.
- **Hierarchical chunks.** Store both file-level and function-level chunks. File-level summaries for broad questions, function-level for specific ones.

---

## 4. LLM: Why Groq (Llama 3.3 70B)?

**Decision:** Groq `llama-3.3-70b-versatile` via OpenAI-compatible API

**Why Groq:**
- Sub-1s inference (~0.5-1s generation) thanks to Groq's custom LPU hardware — brings total query latency to ~2-2.5s, well under the 3s target
- OpenAI-compatible API — uses the same `OpenAILike` adapter as any other provider. Zero custom integration code.
- Llama 3.3 70B has strong code understanding — comparable to proprietary models for code analysis tasks
- Cost-effective: ~$0.59/M input, ~$0.79/M output (~$0.004 per query vs ~$0.02 with proprietary models)
- Free tier sufficient for demo/grading

**Provider-agnostic architecture:** The LLM layer auto-detects from whichever API key is set (Groq > xAI > Anthropic). Switching providers is a config change — set different env vars, no code modifications. This made it trivial to evaluate multiple providers during development.

**Tradeoff:** Open-source model (Llama 3.3 70B) vs proprietary (Claude, Grok). For code analysis, the quality gap is smaller than for general reasoning. The 5x latency improvement and 5x cost reduction make this a clear win for this use case.

**What the interviewer might ask:** "Why not use a local model?" — Explored this (Ollama branch). DeepSeek Coder and CodeLlama would work locally but not on Fly.io (512MB RAM, no GPU). Would need a separate inference server. Not worth the complexity for a demo.

---

## 5. Streaming Architecture

**Decision:** Two-phase SSE streaming instead of single blocking response.

**Phase 1 — Retrieval (~2s):** Embed query with Voyage -> search Pinecone -> return source chunks immediately as an SSE `sources` event.

**Phase 2 — Generation (~0.5-1s):** Build context from retrieved nodes -> stream LLM tokens one at a time as SSE `token` events.

**Total end-to-end: ~2-2.5s.** User sees source chunks at the ~2s mark, with the LLM answer streaming almost immediately after.

**Tradeoff:** More complex than a single `POST` -> JSON response. The frontend needs to handle a `ReadableStream`, parse SSE events, and incrementally render markdown. But the UX improvement is substantial.

**Why SSE instead of WebSockets:** SSE is simpler (one-directional, auto-reconnect, works over HTTP/1.1). We don't need bidirectional communication — the client sends a query and receives a stream back. WebSockets would be overkill.

---

## 6. Mode System: 8 Modes, Same Pipeline

**Decision:** All 8 analysis modes share the same retrieval pipeline. Only the LLM system prompt changes.

**Why not separate pipelines per mode?**
- The retrieval step (Voyage embed -> Pinecone search) is mode-agnostic. The top-5 most relevant chunks for "cobc_abort" are the same whether you want an explanation or a dependency map.
- Building mode-specific retrieval (e.g., a dependency graph index for the "dependencies" mode) would be more accurate but would require separate data structures, indexing, and maintenance. Not worth it for a demo.

**Which modes are from the assignment vs. added:**
- **From assignment table:** Code Explanation, Business Logic Extract, Dependency Mapping, Impact Analysis, Documentation Gen, Translation Hints (6/8 in the assignment table)
- **Added by us:** Cross-Reference Search, Code Summarization (useful and cheap to add)

**Honest assessment of mode quality:**
- **Explain, Summarize, DocGen:** Work well — the LLM is good at these tasks.
- **Business Logic, Translate:** Work reasonably well — the prompts guide the LLM to look for the right things.
- **Dependencies, Impact:** The LLM *guesses* based on what's in the chunks. It can't trace real call graphs. A knowledge graph (like GitNexus uses) would be much more accurate.
- **X-Ref:** Works for identifiers that appear in the top-5 chunks. Misses identifiers that only appear elsewhere. Hybrid search (BM25) would help.

---

## 7. Failure Modes — What Doesn't Work Well

### Exact identifier search
**Problem:** Searching for `cb_source_file` might not find the definition if other chunks are semantically closer.
**Root cause:** Cosine similarity on embeddings measures *meaning*, not *string match*. The definition of `cb_source_file` might have low semantic similarity to the query "cb_source_file" compared to a chunk that *talks about* source files.
**Fix:** Hybrid search (BM25 + vector). Pinecone doesn't support this natively. Would need Weaviate, Qdrant, or a separate BM25 index.

### Cross-file reasoning
**Problem:** "Show me the full call chain from main() to cobc_abort()" can't be answered if the intermediate functions aren't in the top-5 chunks.
**Root cause:** top_k=5 limits how many files are represented. The call chain might traverse 4 files, but we only retrieve 5 chunks — possibly all from the same file.
**Fix:** Increase top_k (more noise), or use query expansion (generate sub-queries for each hop in the chain), or build a call graph.

### Abstract/broad queries
**Problem:** "How does the compiler work?" returns random chunks because no single chunk is a great match for such a broad question.
**Root cause:** Semantic search assumes the query is about something specific. Broad questions have low similarity to everything.
**Fix:** The Summarize mode helps — its prompt tells the LLM to synthesize a high-level view from whatever chunks it gets. But the retrieval itself isn't great for these.

### COBOL test fixtures
**Problem:** Some COBOL test files use non-standard formatting that the regex chunker doesn't recognize. They get treated as single-file chunks.
**Root cause:** The regex expects standard COBOL column conventions. Test fixtures are often free-form.
**Impact:** Lower granularity for those files, but no data loss. The content is still in Pinecone.

### Latency
**Current state:** ~2-2.5s end-to-end, comfortably under the 3-second target.
**Breakdown:** Voyage embedding ~1-1.5s, Pinecone search ~0.3s, Groq generation ~0.5-1s.
**Optimization if needed:** Cache Voyage embeddings for repeated queries (~1s saved). Reduce context (fewer chunks, shorter prompt).

---

## 8. Frontend Decisions

### Why a single HTML file?
No build step, no npm, no React. Ships in the Docker image alongside FastAPI. For a demo with 8 buttons and a text input, a SPA framework adds complexity without benefit.

### Why retro aesthetic?
User's choice. But it actually helps the demo — it's visually distinctive and memorable compared to a generic Tailwind dashboard.

### Why Highlight.js over Prism or Shiki?
Highlight.js is 11KB for C + COBOL. No build step needed. Loaded from CDN. Lazy-highlighted on card expand so it doesn't block initial render.

### The "drill down" feature
Assignment asks for "Ability to drill down into full file context." Since we don't serve the raw source files (they're not in the Docker image — only Pinecone has the vectors), we link to GitHub. Each expanded source card has a "View full file on GitHub" link that opens the exact file at the right line range. GnuCOBOL is public, so this works.

---

## 9. Deployment & Infrastructure

### Why Fly.io?
- Prior experience
- Free tier covers a single 512MB shared-CPU machine
- Docker-based deploys (just `fly deploy`)
- Built-in health checks
- IAD region (US East) is close to Pinecone's servers

### Why the Docker image doesn't contain the codebase
The codebase is only needed during ingestion. Pinecone already has all the vectors. The deployed app just connects to Pinecone at runtime. This keeps the Docker image small (~200MB for Python + dependencies) and means code updates don't require re-ingestion.

### Machine scaling
`min_machines_running = 1` with `machine_idle_timeout = 15m`. This keeps one machine always warm so there's no cold start penalty. The 15-minute idle timeout is generous — if no traffic for 15 minutes, the machine sleeps, but Fly auto-starts it on the next request.

---

## 10. What I'd Do Differently (With More Time)

| Improvement | Why | Effort |
|------------|-----|--------|
| **Hybrid search (BM25 + semantic)** | Fix exact identifier matching | 1-2 days (switch to Weaviate) |
| **Knowledge graph for dependencies** | Real call graphs instead of LLM guesses | 2-3 days (KuzuDB + tree-sitter call extraction) |
| **Re-ranking with Cohere** | Improve precision@5 from 73% to ~85%+ | 2 hours |
| **Query expansion** | Generate sub-queries for complex questions | 4 hours |
| **Hierarchical chunking** | File-level + function-level for different query types | 1 day |
| **Evaluation harness** | Automated precision/recall testing with ground truth | 1 day |
| **Caching layer** | Cache Voyage embeddings + Pinecone results for repeat queries | 4 hours |
| **Claude as LLM** | Better code understanding than Groq/Llama | 5 minutes (config change) |

---

## 11. Cost Awareness

**Development cost:** ~$0.80 (LLM API only). Everything else is free tier.

**Per-query cost:** ~$0.004 (Groq at ~$0.59/M input, ~$0.79/M output). This is ~5x cheaper than proprietary LLMs.

**The cost cliff:** At scale, LLM inference is the largest cost component, but Groq's pricing makes it manageable. At 100 users doing 5 queries/day, it's ~$65/month. At 100K users it's ~$60K/month. Further optimization: smaller model (Llama 3.1 8B on Groq drops it to ~$22K) or caching.

**Key insight for the interview:** Embeddings are a one-time cost. Vector DB storage is cheap. LLM per-query cost is what scales with users — but with Groq's pricing, per-user cost is ~$0.65/mo, making a $2-5/mo subscription viable at any scale.

---

## 12. Technical Choices They Might Probe

**"Why LlamaIndex over LangChain?"**
LlamaIndex is purpose-built for document-to-index-to-query RAG. LangChain is broader (agents, chains, tools). For this use case — ingest documents, build an index, query it — LlamaIndex's API maps directly: `Document -> TextNode -> VectorStoreIndex -> QueryEngine`. Less abstraction overhead.

**"Why not use LangChain's text splitters?"**
I needed function-level granularity. LangChain's `RecursiveCharacterTextSplitter` is character-based, not AST-aware. Their `Language` splitter exists but gives less control than walking the tree-sitter AST directly.

**"How do you handle hallucination?"**
The system prompt explicitly says: "If the retrieved code chunks don't contain enough information to answer confidently, say so. Do not hallucinate or guess about code that isn't in the context." The LLM mostly follows this, but it's not perfect. Showing relevance scores to the user gives them a signal about confidence. If all 5 chunks are <50% similarity, the answer is likely weak.

**"What's your precision@5?"**
~73% on the 6 test scenarios from the assignment. Measured manually: for each query, count how many of the top-5 chunks are genuinely relevant to the question. Best case (exact function lookup): 5/5. Worst case (broad "how does the compiler work?"): 2/5.

**"How would you scale this to 10 codebases?"**
Pinecone supports metadata filtering. Each codebase gets a `codebase` metadata field. At query time, filter by codebase. One index handles all of them. Alternatively, use Pinecone namespaces (one per codebase). The rest of the pipeline is unchanged.

---

## 13. Edge Cases

| Edge Case | What Happens | How We Handle It |
|-----------|-------------|-----------------|
| **C file with broken syntax** (e.g., heavy preprocessor macros that confuse tree-sitter) | AST parse succeeds but misidentifies function boundaries, or fails entirely | Catch the exception, fall back to treating the whole file as one chunk (`file_fallback`). No data lost, just coarser granularity. |
| **Oversized function** (500+ line C function that exceeds chunk limits) | Single chunk is >3000 chars, too large for useful retrieval | Auto-split with SentenceSplitter, preserving original metadata. Chunk type gets `_split` suffix so we know it was subdivided. |
| **Query with no good matches** (e.g., "What's the weather?") | Pinecone returns 5 chunks anyway — all with low similarity scores (<40%) | LLM system prompt says "if context is insufficient, say so." Relevance scores are shown to the user so they can see the low confidence. |
| **Non-UTF-8 encoded source files** | `decode()` would crash during chunking | All file reads use `errors="replace"`, substituting bad bytes with `U+FFFD`. Binary files are filtered out entirely during file discovery. |
