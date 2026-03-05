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
| Dev testing (Groq Llama 3.3 70B) | ~150 | ~600K in + ~300K out | ~$0.60 |
| Production queries (demo users) | ~50 | ~200K in + ~100K out | ~$0.20 |
| **Total LLM** | **~200** | **~1.2M** | **~$0.80** |

Groq pricing: ~$0.59/M input tokens, ~$0.79/M output tokens.

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
| LLM API | ~$0.80 |
| Infrastructure | $0.00 |
| Dev tools | ~$100/mo (subscription, not project-specific) |
| **Project-specific total** | **~$0.80** |

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
| LLM input (Groq Llama 3.3 70B) | 5,000 | $0.59/M tokens | $0.003 |
| LLM output (Groq Llama 3.3 70B) | 1,000 | $0.79/M tokens | $0.001 |
| **Total per query** | | | **~$0.004** |

### Monthly Projections

| | 100 Users | 1,000 Users | 10,000 Users | 100,000 Users |
|---|-----------|-------------|--------------|---------------|
| **Queries/month** | 15,000 | 150,000 | 1,500,000 | 15,000,000 |
| **Embedding (Voyage)** | $0.05 | $0.45 | $4.50 | $45 |
| **Pinecone** | $0 (free) | $70/mo (Standard) | $70 + usage | $230+ (Enterprise) |
| **LLM (Groq Llama 3.3 70B)** | $60 | $600 | $6,000 | $60,000 |
| **Fly.io compute** | $5 | $15 | $60 | $200+ |
| **Total/month** | **~$65** | **~$685** | **~$6,135** | **~$60,475** |
| **Per-user/month** | $0.65 | $0.69 | $0.61 | $0.60 |

### Key Observations

1. **LLM cost dominates but at a much lower level.** At every scale, LLM inference is the largest cost component, but Groq's pricing (~$0.59/$0.79 per M tokens) is dramatically cheaper than proprietary alternatives.

2. **Linear scaling.** Cost scales almost perfectly linearly with users because each query requires a fresh LLM call. There's no caching benefit for unique code questions.

3. **Per-user cost is ~$0.65/mo.** A $2-5/mo subscription covers costs with healthy margin. Compared to proprietary LLMs at ~$3/mo per user, Groq makes the unit economics viable at any scale.

### Cost Optimization Strategies

| Strategy | Savings | Tradeoff |
|----------|---------|----------|
| **Switch to smaller model** (Llama 3.1 8B on Groq) | 60-70% on LLM costs | Lower answer quality, especially for complex code analysis |
| **Response caching** (exact query dedup) | 10-20% | Stale answers if codebase updates; cache key design is tricky |
| **Reduce context window** (top_k=3 instead of 5) | 30-40% on LLM input | Fewer source chunks, may miss relevant code |
| **Streaming token limits** (cap output at 500 tokens) | 50% on LLM output | Truncated explanations for complex queries |
| **Rate limiting** (10 queries/user/day) | Caps exposure | Limits power users |

### Optimized Projection (with Llama 3.1 8B on Groq + top_k=3)

| | 100 Users | 1,000 Users | 10,000 Users | 100,000 Users |
|---|-----------|-------------|--------------|---------------|
| **Total/month** | **~$25** | **~$230** | **~$2,200** | **~$22,000** |
| **Per-user/month** | $0.25 | $0.23 | $0.22 | $0.22 |

Switching to a smaller model on Groq drops per-user cost from $0.65/mo to ~$0.22/mo — a 3x reduction — at the expense of answer quality.
