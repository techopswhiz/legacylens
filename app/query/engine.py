"""Query engine: connects to Pinecone, retrieves context, generates answers."""

import logging
import time
from dataclasses import dataclass
from typing import Generator

from pinecone import Pinecone
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.llms import ChatMessage
from llama_index.core.prompts import PromptTemplate
from llama_index.embeddings.voyageai import VoyageEmbedding
from llama_index.llms.openai_like import OpenAILike
from llama_index.vector_stores.pinecone import PineconeVectorStore

from app.config import settings
from app.query.prompts import SYSTEM_PROMPT, QUERY_TEMPLATE, MODE_PROMPTS

logger = logging.getLogger(__name__)


@dataclass
class SourceChunk:
    """A retrieved source code chunk with metadata."""
    file_path: str
    line_start: int
    line_end: int
    language: str
    chunk_type: str
    function_name: str | None
    text: str
    score: float


@dataclass
class QueryResult:
    """Result of a query: answer text + source chunks."""
    answer: str
    sources: list[SourceChunk]
    query: str
    latency_ms: float


class LegacyLensEngine:
    """
    RAG query engine for legacy codebases.

    Connects to an existing Pinecone index (populated by ingestion pipeline),
    retrieves relevant chunks, and generates answers via LLM.
    """

    def __init__(self):
        self._query_engine = None
        self._index = None

    def initialize(self):
        """Set up all components: Pinecone, embeddings, LLM, query engine."""
        logger.info("Initializing LegacyLens query engine...")

        # Embedding model (same as ingestion)
        embed_model = VoyageEmbedding(
            model_name=settings.EMBEDDING_MODEL,
            voyage_api_key=settings.VOYAGE_API_KEY,
        )
        # Patch: voyageai 0.2.x doesn't support output_dtype/output_dimension kwargs
        import types

        def _patched_embed(self, texts, input_type):
            embeddings = []
            for batch, _ in self._build_batches(texts):
                result = self._client.embed(
                    batch,
                    model=self.model_name,
                    input_type=input_type,
                    truncation=self.truncation,
                )
                embeddings.extend(result.embeddings)
            return embeddings

        embed_model._embed = types.MethodType(_patched_embed, embed_model)
        Settings.embed_model = embed_model

        # LLM — use xAI Grok via OpenAI-compatible API
        llm = OpenAILike(
            model=settings.LLM_MODEL,
            api_key=settings.XAI_API_KEY,
            api_base="https://api.x.ai/v1",
            max_tokens=4096,
            temperature=0.1,
            is_chat_model=True,
            context_window=131072,
        )
        Settings.llm = llm

        # Connect to existing Pinecone index
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        pinecone_index = pc.Index(settings.PINECONE_INDEX_NAME)

        # Build query index from vector store
        vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
        self._index = VectorStoreIndex.from_vector_store(vector_store)

        # Create query engine with custom prompts
        self._query_engine = self._index.as_query_engine(
            similarity_top_k=settings.TOP_K,
            text_qa_template=PromptTemplate(
                SYSTEM_PROMPT + "\n\n" + QUERY_TEMPLATE
            ),
        )

        logger.info("Query engine ready.")

    def _node_to_source(self, node_with_score) -> SourceChunk:
        """Convert a LlamaIndex NodeWithScore to a SourceChunk."""
        node = node_with_score.node
        meta = node.metadata or {}
        return SourceChunk(
            file_path=meta.get("file_path", "unknown"),
            line_start=int(meta.get("line_start", 0)),
            line_end=int(meta.get("line_end", 0)),
            language=meta.get("language", "unknown"),
            chunk_type=meta.get("chunk_type", "unknown"),
            function_name=meta.get("function_name"),
            text=node.get_content(),
            score=node_with_score.score or 0.0,
        )

    @staticmethod
    def _keyword_rerank(
        query_text: str, nodes_with_scores: list, final_k: int
    ) -> list:
        """Re-rank by blending semantic score with keyword overlap.

        Fetches more candidates than needed from Pinecone, then boosts
        chunks that contain literal query terms (poor man's hybrid search).
        """
        import re
        # Extract meaningful terms (3+ chars, alphanumeric/underscore)
        query_terms = [
            t.lower() for t in re.findall(r'\w{3,}', query_text)
            if t.lower() not in {'the', 'this', 'what', 'where', 'how',
                                  'does', 'are', 'all', 'from', 'with',
                                  'for', 'that', 'show'}
        ]
        if not query_terms:
            return nodes_with_scores[:final_k]

        for nws in nodes_with_scores:
            text_lower = nws.node.get_content().lower()
            meta = nws.node.metadata or {}
            func_name = (meta.get("function_name") or "").lower()
            # Count how many query terms appear in the chunk text or function name
            hits = sum(
                1 for t in query_terms
                if t in text_lower or t in func_name
            )
            keyword_score = hits / len(query_terms)
            # Blend: 70% semantic + 30% keyword
            nws.score = 0.7 * (nws.score or 0.0) + 0.3 * keyword_score

        nodes_with_scores.sort(key=lambda x: x.score, reverse=True)
        return nodes_with_scores[:final_k]

    def retrieve_chunks(
        self, query_text: str, top_k: int | None = None
    ) -> tuple[list[SourceChunk], list]:
        """Retrieve relevant chunks without generating an answer.

        Fetches 3x candidates from Pinecone, then re-ranks with keyword
        overlap to approximate hybrid search. Returns (source_chunks,
        raw_nodes_with_scores) so callers can pass raw nodes to stream_answer().
        """
        if self._index is None:
            raise RuntimeError("Engine not initialized. Call initialize() first.")

        final_k = top_k or settings.TOP_K
        # Over-fetch for re-ranking headroom
        fetch_k = final_k * 3

        retriever = self._index.as_retriever(similarity_top_k=fetch_k)
        nodes_with_scores = retriever.retrieve(query_text)

        # Re-rank with keyword overlap
        nodes_with_scores = self._keyword_rerank(
            query_text, nodes_with_scores, final_k
        )

        sources = [self._node_to_source(n) for n in nodes_with_scores]
        return sources, nodes_with_scores

    def stream_answer(
        self, query_text: str, nodes_with_scores: list, mode: str = "explain"
    ) -> Generator[str, None, None]:
        """Stream LLM answer token-by-token given pre-retrieved nodes."""
        # Build context string from nodes (same format LlamaIndex would use)
        context_parts = []
        for nws in nodes_with_scores:
            node = nws.node
            meta = node.metadata or {}
            func = meta.get("function_name")
            header = (
                f"### {meta.get('file_path', 'unknown')}"
                f":{meta.get('line_start', '?')}-{meta.get('line_end', '?')}"
            )
            details = (
                f"Language: {meta.get('language', 'unknown')} | "
                f"Type: {meta.get('chunk_type', 'unknown')}"
            )
            if func:
                details += f" | Function: {func}"
            context_parts.append(
                f"{header}\n{details}\n```\n{node.get_content()}\n```"
            )
        context_str = "\n\n".join(context_parts)

        # Pick mode-specific system prompt
        system_prompt = MODE_PROMPTS.get(mode, SYSTEM_PROMPT)

        # Build full prompt
        full_prompt = (
            system_prompt + "\n\n"
            + QUERY_TEMPLATE.format(
                context_str=context_str,
                query_str=query_text,
            )
        )

        # Stream from LLM
        messages = [ChatMessage(role="user", content=full_prompt)]
        stream_resp = Settings.llm.stream_chat(messages)
        for token in stream_resp:
            if token.delta:
                yield token.delta

    def query(self, query_text: str, top_k: int | None = None) -> QueryResult:
        """
        Run a query against the codebase (non-streaming).

        Args:
            query_text: Natural language question about the codebase
            top_k: Override default number of chunks to retrieve

        Returns:
            QueryResult with answer and source chunks
        """
        if self._query_engine is None:
            raise RuntimeError("Engine not initialized. Call initialize() first.")

        t0 = time.time()

        # If custom top_k, rebuild engine temporarily
        engine = self._query_engine
        if top_k and top_k != settings.TOP_K:
            engine = self._index.as_query_engine(
                similarity_top_k=top_k,
                text_qa_template=PromptTemplate(
                    SYSTEM_PROMPT + "\n\n" + QUERY_TEMPLATE
                ),
            )

        # Execute query
        response = engine.query(query_text)

        # Extract source chunks from response
        sources = [self._node_to_source(n) for n in response.source_nodes]

        latency_ms = (time.time() - t0) * 1000

        result = QueryResult(
            answer=str(response),
            sources=sources,
            query=query_text,
            latency_ms=latency_ms,
        )

        logger.info(
            f"Query completed in {latency_ms:.0f}ms, "
            f"{len(sources)} sources retrieved"
        )

        return result
