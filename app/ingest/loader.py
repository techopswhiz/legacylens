"""File discovery and loading for legacy codebases."""

import logging
from pathlib import Path

from llama_index.core.schema import Document

logger = logging.getLogger(__name__)

# Extensions we want to index, mapped to language name
EXTENSION_MAP: dict[str, str] = {
    ".c": "c",
    ".h": "c_header",
    ".cob": "cobol",
    ".cbl": "cobol",
    ".cpy": "cobol_copybook",
    ".y": "yacc",
    ".l": "lex",
    ".def": "definition",
}

# Directories to skip entirely
SKIP_DIRS = {
    ".git",
    "build",
    "autom4te.cache",
    "po",          # translations, not code
    ".deps",
    "doc",
    "m4",
}

# Max file size (500KB) — skip anything larger (likely generated)
MAX_FILE_SIZE = 500_000


def detect_language(ext: str) -> str:
    """Map file extension to language identifier."""
    return EXTENSION_MAP.get(ext, "unknown")


def load_codebase(codebase_path: Path) -> list[Document]:
    """
    Recursively scan codebase directory, load source files as Documents.

    Returns list of LlamaIndex Document objects with metadata:
    - file_path: relative path from codebase root
    - file_extension: e.g. '.c'
    - language: detected language name
    - file_size: size in bytes
    """
    if not codebase_path.exists():
        raise FileNotFoundError(f"Codebase not found at {codebase_path}")

    documents: list[Document] = []
    skipped: dict[str, int] = {"binary": 0, "too_large": 0, "encoding": 0}

    for file_path in sorted(codebase_path.rglob("*")):
        if not file_path.is_file():
            continue

        # Skip excluded directories
        if any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
            continue

        # Only process known extensions
        ext = file_path.suffix.lower()
        if ext not in EXTENSION_MAP:
            continue

        # Skip oversized files
        file_size = file_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            skipped["too_large"] += 1
            logger.warning(f"Skipping large file ({file_size} bytes): {file_path}")
            continue

        # Skip empty files
        if file_size == 0:
            continue

        # Read file content
        rel_path = str(file_path.relative_to(codebase_path))
        language = detect_language(ext)

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = file_path.read_text(encoding="latin-1")
            except Exception:
                skipped["encoding"] += 1
                logger.warning(f"Encoding error, skipping: {rel_path}")
                continue

        # Quick binary check — if there are null bytes, skip
        if "\x00" in content:
            skipped["binary"] += 1
            logger.debug(f"Skipping binary file: {rel_path}")
            continue

        doc = Document(
            text=content,
            metadata={
                "file_path": rel_path,
                "file_extension": ext,
                "language": language,
                "file_size": file_size,
            },
        )
        documents.append(doc)

    logger.info(
        f"Loaded {len(documents)} files "
        f"(skipped: {skipped['binary']} binary, "
        f"{skipped['too_large']} too large, "
        f"{skipped['encoding']} encoding errors)"
    )

    return documents


def print_stats(documents: list[Document]) -> None:
    """Print summary statistics of loaded documents."""
    by_lang: dict[str, int] = {}
    total_size = 0
    for doc in documents:
        lang = doc.metadata["language"]
        by_lang[lang] = by_lang.get(lang, 0) + 1
        total_size += doc.metadata["file_size"]

    print(f"\n{'='*40}")
    print(f"Loaded {len(documents)} files ({total_size:,} bytes)")
    print(f"{'='*40}")
    for lang, count in sorted(by_lang.items(), key=lambda x: -x[1]):
        print(f"  {lang:20s}: {count} files")
    print()
