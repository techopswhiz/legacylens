#!/usr/bin/env python3
"""CLI: Run the full ingestion pipeline."""

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ingest.pipeline import run_ingestion


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("=" * 50)
    print("LegacyLens — Ingestion Pipeline")
    print("=" * 50)

    try:
        stats = run_ingestion()
    except ValueError as e:
        print(f"\n❌ Config error: {e}")
        print("   Copy .env.example to .env and fill in your API keys.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ingestion failed: {e}")
        logging.exception("Ingestion error")
        sys.exit(1)


if __name__ == "__main__":
    main()
