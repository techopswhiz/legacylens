"""Configuration for LegacyLens — loads from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present (dev mode)
load_dotenv()

# Project root (parent of app/)
PROJECT_ROOT = Path(__file__).parent.parent


class Settings:
    """Application settings loaded from environment variables."""

    # API Keys
    PINECONE_API_KEY: str = os.environ.get("PINECONE_API_KEY", "")
    VOYAGE_API_KEY: str = os.environ.get("VOYAGE_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
    XAI_API_KEY: str = os.environ.get("XAI_API_KEY", "")
    GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
    GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY", "")

    # Pinecone
    PINECONE_INDEX_NAME: str = os.environ.get("PINECONE_INDEX_NAME", "legacylens")

    # Embedding
    EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "voyage-code-3")
    EMBEDDING_DIMENSION: int = int(os.environ.get("EMBEDDING_DIMENSION", "1024"))

    # LLM
    LLM_MODEL: str = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
    LLM_API_BASE: str = os.environ.get("LLM_API_BASE", "")  # Auto-detect if empty
    LLM_CONTEXT_WINDOW: int = int(os.environ.get("LLM_CONTEXT_WINDOW", "131072"))
    LLM_MAX_TOKENS: int = int(os.environ.get("LLM_MAX_TOKENS", "1024"))

    # Retrieval
    TOP_K: int = int(os.environ.get("TOP_K", "5"))

    # Codebase
    CODEBASE_PATH: Path = PROJECT_ROOT / os.environ.get(
        "CODEBASE_PATH", "codebase/gnucobol"
    )

    # -- Derived LLM properties (auto-detect provider from API keys) --

    @property
    def llm_api_key(self) -> str:
        """Return the active LLM API key, matched to the resolved API base URL.

        If LLM_API_BASE is explicitly set, infer the right key from the URL.
        Otherwise, fall back to priority order: Groq > xAI > Anthropic.
        """
        if self.LLM_API_BASE:
            # Explicit base URL set — match key to provider
            base = self.LLM_API_BASE.lower()
            if "groq" in base and self.GROQ_API_KEY:
                return self.GROQ_API_KEY
            if "x.ai" in base and self.XAI_API_KEY:
                return self.XAI_API_KEY
        # Auto-detect: first available key wins
        return self.GROQ_API_KEY or self.XAI_API_KEY or self.ANTHROPIC_API_KEY

    @property
    def llm_api_base(self) -> str:
        """Return the LLM API base URL, auto-detected from API key if not set."""
        if self.LLM_API_BASE:
            return self.LLM_API_BASE
        if self.GROQ_API_KEY:
            return "https://api.groq.com/openai/v1"
        if self.XAI_API_KEY:
            return "https://api.x.ai/v1"
        # Anthropic uses its own adapter, but return empty for OpenAILike fallback
        return ""

    def validate(self) -> list[str]:
        """Return list of missing required config values."""
        missing = []
        if not self.PINECONE_API_KEY:
            missing.append("PINECONE_API_KEY")
        if not self.VOYAGE_API_KEY:
            missing.append("VOYAGE_API_KEY")
        if not self.GROQ_API_KEY and not self.XAI_API_KEY and not self.ANTHROPIC_API_KEY:
            missing.append("GROQ_API_KEY, XAI_API_KEY, or ANTHROPIC_API_KEY")
        return missing

    def __repr__(self) -> str:
        return (
            f"Settings(\n"
            f"  PINECONE_INDEX={self.PINECONE_INDEX_NAME},\n"
            f"  EMBEDDING_MODEL={self.EMBEDDING_MODEL},\n"
            f"  EMBEDDING_DIM={self.EMBEDDING_DIMENSION},\n"
            f"  LLM_MODEL={self.LLM_MODEL},\n"
            f"  LLM_API_BASE={self.llm_api_base},\n"
            f"  LLM_CONTEXT_WINDOW={self.LLM_CONTEXT_WINDOW},\n"
            f"  TOP_K={self.TOP_K},\n"
            f"  CODEBASE_PATH={self.CODEBASE_PATH},\n"
            f"  API_KEYS={'all set' if not self.validate() else 'MISSING: ' + ', '.join(self.validate())}\n"
            f")"
        )


settings = Settings()
