# LegacyLens — AI Cost Analysis

## Development & Testing Costs (Actual Spend)

### Embedding Costs

| Item | Tokens | Cost |
|------|--------|------|
| GnuCOBOL ingestion (one-time) | ~4M tokens | $0.00 |
| Re-ingestion during dev (2x) | ~8M tokens | $0.00 |
| Query embeddings during testing (~200 queries) | ~40K tokens | $0.00 |
| **Total embedding** | **~12M tokens** | **$0.00** |

Voyage Code-3 free tier includes 200M tokens. We used ~6% of the free allocation.

### LLM Costs

| Item | Queries | Est. Tokens | Cost |
|------|---------|-------------|------|
| Dev testing (xAI Grok) | ~150 | ~600K in + ~300K out | ~$1.50 |
| Production queries (demo users) | ~50 | ~200K in + ~100K out | ~$0.50 |
| **Total LLM** | **~200** | **~1.2M** | **~$2.00** |

xAI Grok pricing: ~$2/M input tokens, ~$10/M output tokens (estimated from xAI published rates).

### Infrastructure Costs

| Service | Tier | Monthly Cost |
|---------|------|-------------|
| Pinecone | Free (Starter) | $0.00 |
| Fly.io | 1x shared-cpu-1x, 512MB | $0.00 (free allowance) |
| Voyage AI | Free tier | $0.00 |
| GitHub | Free | $0.00 |
| **Total infra** | | **$0.00/mo** |

### Development Tools

| Tool | Cost | Notes |
|------|------|-------|
| Claude Code (Pro Max subscription) | ~$100/mo | Primary development assistant |

### Total Development Spend

| Category | Cost |
|----------|------|
| Embeddings | $0.00 |
| LLM API | ~$2.00 |
| Infrastructure | $0.00 |
| Dev tools | ~$100/mo (subscription, not project-specific) |
| **Project-specific total** | **~$2.00** |

---

## Production Cost Projections

### Assumptions

- **Queries per user per day:** 5 (power users analyzing code)
- **Average tokens per query:** ~5,000 input (context + prompt), ~1,000 output (LLM response)
- **Embedding per query:** ~50 tokens (query text only — codebase already indexed)
- **New code ingestion:** 10K tokens/month (incremental updates)
- **30-day month**

### Per-Query Cost Breakdown

| Component | Tokens | Unit Cost | Per-Query Cost |
|-----------|--------|-----------|---------------|
| Query embedding (Voyage) | 50 | $0.06/M tokens | $0.000003 |
| Pinecone search | 1 query | ~$0.000008/query | $0.000008 |
| LLM input (xAI Grok) | 5,000 | $2/M tokens | $0.01 |
| LLM output (xAI Grok) | 1,000 | $10/M tokens | $0.01 |
| **Total per query** | | | **~$0.02** |

### Monthly Projections

| | 100 Users | 1,000 Users | 10,000 Users | 100,000 Users |
|---|-----------|-------------|--------------|---------------|
| **Queries/month** | 15,000 | 150,000 | 1,500,000 | 15,000,000 |
| **Embedding (Voyage)** | $0.05 | $0.45 | $4.50 | $45 |
| **Pinecone** | $0 (free) | $70/mo (Standard) | $70 + usage | $230+ (Enterprise) |
| **LLM (xAI Grok)** | $300 | $3,000 | $30,000 | $300,000 |
| **Fly.io compute** | $5 | $15 | $60 | $200+ |
| **Total/month** | **~$305** | **~$3,085** | **~$30,135** | **~$300,475** |
| **Per-user/month** | $3.05 | $3.09 | $3.01 | $3.00 |

### Key Observations

1. **LLM cost dominates.** At every scale, 98%+ of cost is LLM inference. Embedding and vector search are negligible.

2. **Linear scaling.** Cost scales almost perfectly linearly with users because each query requires a fresh LLM call. There's no caching benefit for unique code questions.

3. **Per-user cost is flat (~$3/mo).** This makes pricing straightforward: a $5-10/mo subscription easily covers costs with margin.

### Cost Optimization Strategies

| Strategy | Savings | Tradeoff |
|----------|---------|----------|
| **Switch to smaller LLM** (GPT-4o-mini, Haiku) | 80-90% on LLM costs | Lower answer quality, especially for complex code analysis |
| **Response caching** (exact query dedup) | 10-20% | Stale answers if codebase updates; cache key design is tricky |
| **Reduce context window** (top_k=3 instead of 5) | 30-40% on LLM input | Fewer source chunks, may miss relevant code |
| **Streaming token limits** (cap output at 500 tokens) | 50% on LLM output | Truncated explanations for complex queries |
| **Rate limiting** (10 queries/user/day) | Caps exposure | Limits power users |
| **Local/self-hosted LLM** (Llama, Mistral) | 90%+ on LLM costs | Requires GPU infrastructure ($200-500/mo for decent inference), higher latency |

### Optimized Projection (with GPT-4o-mini + top_k=3)

| | 100 Users | 1,000 Users | 10,000 Users | 100,000 Users |
|---|-----------|-------------|--------------|---------------|
| **Total/month** | **~$35** | **~$320** | **~$3,100** | **~$31,000** |
| **Per-user/month** | $0.35 | $0.32 | $0.31 | $0.31 |

Switching to a cheaper LLM drops per-user cost from $3/mo to $0.31/mo — a 10x reduction — at the expense of answer quality.
