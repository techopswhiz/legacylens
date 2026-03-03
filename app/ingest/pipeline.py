"""Ingestion pipeline: load → chunk → embed → store in Pinecone."""

import logging
import time
from pathlib import Path

from pinecone import Pinecone, ServerlessSpec
from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.schema import TextNode
from llama_index.embeddings.voyageai import VoyageEmbedding
from llama_index.vector_stores.pinecone import PineconeVectorStore

from app.config import settings
from app.ingest.loader import load_codebase, print_stats
from app.ingest.chunker import chunk_documents

logger = logging.getLogger(__name__)


def init_pinecone_index():
    """
    Connect to Pinecone and create the index if it doesn't exist.
    Returns the Pinecone Index object.
    """
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)

    # Check if index exists
    existing = [idx.name for idx in pc.list_indexes()]
    if settings.PINECONE_INDEX_NAME not in existing:
        logger.info(f"Creating Pinecone index '{settings.PINECONE_INDEX_NAME}'...")
        pc.create_index(
            name=settings.PINECONE_INDEX_NAME,
            dimension=settings.EMBEDDING_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        # Wait for index to be ready
        while not pc.describe_index(settings.PINECONE_INDEX_NAME).status.get("ready"):
            logger.info("Waiting for index to be ready...")
            time.sleep(2)
        logger.info("Index created and ready.")
    else:
        logger.info(f"Using existing Pinecone index '{settings.PINECONE_INDEX_NAME}'")

    return pc.Index(settings.PINECONE_INDEX_NAME)


def _patched_embed(self, texts, input_type):
    """Patched _embed that doesn't pass unsupported kwargs to voyageai 0.2.x.
    Includes retry with backoff for rate-limited accounts."""
    import time as _time
    embeddings = []
    for batch_idx, (batch, _) in enumerate(self._build_batches(texts)):
        max_retries = 5
        for attempt in range(max_retries):
            try:
                result = self._client.embed(
                    batch,
                    model=self.model_name,
                    input_type=input_type,
                    truncation=self.truncation,
                )
                embeddings.extend(result.embeddings)
                break
            except Exception as e:
                if "RateLimit" in type(e).__name__ and attempt < max_retries - 1:
                    wait = 20 * (attempt + 1)  # 20s, 40s, 60s...
                    logger.warning(f"Rate limited on batch {batch_idx}, waiting {wait}s (attempt {attempt+1})...")
                    _time.sleep(wait)
                else:
                    raise
    return embeddings


def init_embedding_model() -> VoyageEmbedding:
    """Initialize VoyageAI embedding model."""
    embed_model = VoyageEmbedding(
        model_name=settings.EMBEDDING_MODEL,
        voyage_api_key=settings.VOYAGE_API_KEY,
        embed_batch_size=64,
    )
    # Patch: voyageai 0.2.x doesn't support output_dtype/output_dimension
    import types
    embed_model._embed = types.MethodType(_patched_embed, embed_model)
    return embed_model


def run_ingestion(codebase_path: Path | None = None) -> dict:
    """
    Run the full ingestion pipeline:
    1. Load files from codebase
    2. Chunk into nodes
    3. Embed and store in Pinecone

    Returns stats dict.
    """
    codebase_path = codebase_path or settings.CODEBASE_PATH

    # Validate config
    missing = settings.validate()
    if missing:
        raise ValueError(f"Missing required config: {', '.join(missing)}")

    # Step 1: Load files
    print("\n📂 Loading codebase files...")
    t0 = time.time()
    documents = load_codebase(codebase_path)
    print_stats(documents)
    load_time = time.time() - t0

    # Step 2: Chunk documents
    print("✂️  Chunking documents...")
    t1 = time.time()
    nodes = chunk_documents(documents)
    chunk_time = time.time() - t1
    print(f"   Created {len(nodes)} chunks in {chunk_time:.1f}s")

    # Filter out very small chunks (likely just whitespace/noise)
    nodes = [n for n in nodes if len(n.text.strip()) > 20]
    print(f"   After filtering: {len(nodes)} chunks")

    # Step 3: Initialize services
    print("\n🔗 Connecting to Pinecone...")
    pinecone_index = init_pinecone_index()

    print("🧠 Initializing embedding model...")
    embed_model = init_embedding_model()
    Settings.embed_model = embed_model

    # Step 4: Create vector store and build index
    print("\n🚀 Embedding and upserting to Pinecone...")
    print(f"   This will embed {len(nodes)} chunks — may take a few minutes...")
    t2 = time.time()

    vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # Build index from nodes — this auto-embeds and upserts
    _index = VectorStoreIndex(
        nodes=nodes,
        storage_context=storage_context,
        show_progress=True,
    )
    embed_time = time.time() - t2

    total_time = time.time() - t0

    stats = {
        "files_loaded": len(documents),
        "chunks_created": len(nodes),
        "load_time": load_time,
        "chunk_time": chunk_time,
        "embed_time": embed_time,
        "total_time": total_time,
    }

    print(f"\n{'='*40}")
    print(f"✅ Ingestion complete!")
    print(f"   Files: {stats['files_loaded']}")
    print(f"   Chunks: {stats['chunks_created']}")
    print(f"   Load:  {stats['load_time']:.1f}s")
    print(f"   Chunk: {stats['chunk_time']:.1f}s")
    print(f"   Embed: {stats['embed_time']:.1f}s")
    print(f"   Total: {stats['total_time']:.1f}s")
    print(f"{'='*40}")

    return stats
