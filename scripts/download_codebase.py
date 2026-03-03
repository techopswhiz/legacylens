#!/usr/bin/env python3
"""Download the GnuCOBOL codebase for indexing."""

import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/OCamlPro/gnucobol.git"
TARGET_DIR = Path(__file__).parent.parent / "codebase" / "gnucobol"


def main():
    if TARGET_DIR.exists() and any(TARGET_DIR.iterdir()):
        print(f"✓ Codebase already exists at {TARGET_DIR}")
        return

    print(f"Cloning GnuCOBOL from {REPO_URL}...")
    TARGET_DIR.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["git", "clone", "--depth", "1", REPO_URL, str(TARGET_DIR)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Error cloning: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Cloned to {TARGET_DIR}")

    # Quick stats
    file_count = sum(1 for _ in TARGET_DIR.rglob("*") if _.is_file())
    print(f"  Total files: {file_count}")


if __name__ == "__main__":
    main()
