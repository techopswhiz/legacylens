"""FastAPI application for LegacyLens."""

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import settings
from app.query.engine import LegacyLensEngine

logger = logging.getLogger(__name__)

# Global engine instance
engine = LegacyLensEngine()


# --- Request/Response Models ---

VALID_MODES = {"explain", "business_logic", "dependencies", "translate", "xref", "summarize", "impact", "docgen"}


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: str = Field(default="explain")
    model: str | None = Field(default=None, description="LLM model ID (from /api/models)")


class SourceResponse(BaseModel):
    file_path: str
    line_start: int
    line_end: int
    language: str
    chunk_type: str
    function_name: str | None
    text: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]
    query: str
    latency_ms: float


class HealthResponse(BaseModel):
    status: str
    engine_ready: bool


# --- Lifespan ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize query engine on startup."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    missing = settings.validate()
    if missing:
        logger.error(f"Missing API keys: {', '.join(missing)}")
        logger.error("Set environment variables and restart.")
        # Don't crash — let health endpoint report the issue
        yield
        return

    try:
        engine.initialize()
        logger.info("LegacyLens is ready to accept queries.")
    except Exception as e:
        logger.error(f"Failed to initialize engine: {e}")

    yield

    logger.info("Shutting down LegacyLens.")


# --- App ---

app = FastAPI(
    title="LegacyLens",
    description="RAG-powered system for querying legacy enterprise codebases",
    version="1.0.0",
    lifespan=lifespan,
)


# --- Routes ---

@app.post("/api/query", response_model=QueryResponse)
async def query_codebase(request: QueryRequest):
    """Query the legacy codebase with a natural language question."""
    if engine._query_engine is None:
        raise HTTPException(
            status_code=503,
            detail="Query engine not initialized. Check API keys and Pinecone index.",
        )

    try:
        result = engine.query(request.query, top_k=request.top_k)
    except Exception as e:
        logger.exception(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

    return QueryResponse(
        answer=result.answer,
        sources=[
            SourceResponse(
                file_path=s.file_path,
                line_start=s.line_start,
                line_end=s.line_end,
                language=s.language,
                chunk_type=s.chunk_type,
                function_name=s.function_name,
                text=s.text,
                score=s.score,
            )
            for s in result.sources
        ],
        query=result.query,
        latency_ms=result.latency_ms,
    )


@app.post("/api/query/stream")
async def query_stream(request: QueryRequest):
    """Query with retrieval + LLM generation.

    When STREAM_RESPONSE=true, streams via Server-Sent Events:
      event: sources  — JSON array of source chunks
      event: token    — single LLM token string (repeated)
      event: done     — JSON with latency_ms

    When STREAM_RESPONSE=false (default), returns a single JSON response
    matching the same shape as /api/query.
    """
    if engine._query_engine is None:
        raise HTTPException(
            status_code=503,
            detail="Query engine not initialized. Check API keys and Pinecone index.",
        )

    mode = request.mode if request.mode in VALID_MODES else "explain"

    # --- Non-streaming path ---
    if not settings.STREAM_RESPONSE:
        t0 = time.time()
        try:
            sources, nodes, timing = engine.retrieve_chunks(request.query, request.top_k)
            t_gen = time.time()
            answer = engine.generate_answer(
                request.query, nodes, mode=mode, model=request.model,
            )
            generation_ms = (time.time() - t_gen) * 1000
            latency_ms = (time.time() - t0) * 1000

            logger.info(
                f"Query completed in {latency_ms:.0f}ms "
                f"(retrieval={timing['retrieval_ms']:.0f}ms, "
                f"rerank={timing['rerank_ms']:.0f}ms, "
                f"generation={generation_ms:.0f}ms), "
                f"{len(sources)} sources retrieved"
            )

            return {
                "answer": answer,
                "sources": [
                    {
                        "file_path": s.file_path,
                        "line_start": s.line_start,
                        "line_end": s.line_end,
                        "language": s.language,
                        "chunk_type": s.chunk_type,
                        "function_name": s.function_name,
                        "text": s.text,
                        "score": s.score,
                    }
                    for s in sources
                ],
                "query": request.query,
                "latency_ms": latency_ms,
                "timing": {**timing, "generation_ms": generation_ms},
            }
        except Exception as e:
            logger.exception(f"Query failed: {e}")
            raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

    # --- Streaming path (SSE) ---
    def event_generator():
        t0 = time.time()

        try:
            sources, nodes, timing = engine.retrieve_chunks(request.query, request.top_k)

            yield f"event: timing\ndata: {json.dumps(timing)}\n\n"

            sources_data = [
                {
                    "file_path": s.file_path,
                    "line_start": s.line_start,
                    "line_end": s.line_end,
                    "language": s.language,
                    "chunk_type": s.chunk_type,
                    "function_name": s.function_name,
                    "text": s.text,
                    "score": s.score,
                }
                for s in sources
            ]
            yield f"event: sources\ndata: {json.dumps(sources_data)}\n\n"

            t_gen = time.time()
            for token in engine.stream_answer(
                request.query, nodes, mode=mode, model=request.model,
            ):
                yield f"event: token\ndata: {json.dumps(token)}\n\n"
            generation_ms = (time.time() - t_gen) * 1000

            latency_ms = (time.time() - t0) * 1000
            yield f"event: done\ndata: {json.dumps({'latency_ms': latency_ms, 'generation_ms': generation_ms})}\n\n"

            logger.info(
                f"Streaming query completed in {latency_ms:.0f}ms "
                f"(retrieval={timing['retrieval_ms']:.0f}ms, "
                f"rerank={timing['rerank_ms']:.0f}ms, "
                f"generation={generation_ms:.0f}ms), "
                f"{len(sources)} sources retrieved"
            )
        except Exception as e:
            logger.exception(f"Stream query failed: {e}")
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        engine_ready=engine._query_engine is not None,
    )


@app.get("/api/models")
async def list_models():
    """Return available LLM models for the UI dropdown."""
    return engine.get_available_models()


@app.get("/api/config")
async def get_config():
    """Return client-relevant configuration."""
    return {"stream_response": settings.STREAM_RESPONSE}


# Serve static frontend
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the frontend HTML."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "LegacyLens API is running. No frontend found."}
