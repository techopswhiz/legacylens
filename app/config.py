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

    # Pinecone
    PINECONE_INDEX_NAME: str = os.environ.get("PINECONE_INDEX_NAME", "legacylens")

    # Embedding
    EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "voyage-code-3")
    EMBEDDING_DIMENSION: int = int(os.environ.get("EMBEDDING_DIMENSION", "1024"))

    # LLM
    LLM_MODEL: str = os.environ.get("LLM_MODEL", "grok-3-mini")

    # Retrieval
    TOP_K: int = int(os.environ.get("TOP_K", "5"))

    # Codebase
    CODEBASE_PATH: Path = PROJECT_ROOT / os.environ.get(
        "CODEBASE_PATH", "codebase/gnucobol"
    )

    def validate(self) -> list[str]:
        """Return list of missing required config values."""
        missing = []
        if not self.PINECONE_API_KEY:
            missing.append("PINECONE_API_KEY")
        if not self.VOYAGE_API_KEY:
            missing.append("VOYAGE_API_KEY")
        if not self.ANTHROPIC_API_KEY and not self.XAI_API_KEY:
            missing.append("ANTHROPIC_API_KEY or XAI_API_KEY")
        return missing

    def __repr__(self) -> str:
        return (
            f"Settings(\n"
            f"  PINECONE_INDEX={self.PINECONE_INDEX_NAME},\n"
            f"  EMBEDDING_MODEL={self.EMBEDDING_MODEL},\n"
            f"  EMBEDDING_DIM={self.EMBEDDING_DIMENSION},\n"
            f"  LLM_MODEL={self.LLM_MODEL},\n"
            f"  TOP_K={self.TOP_K},\n"
            f"  CODEBASE_PATH={self.CODEBASE_PATH},\n"
            f"  API_KEYS={'all set' if not self.validate() else 'MISSING: ' + ', '.join(self.validate())}\n"
            f")"
        )


settings = Settings()
