"""Syntax-aware chunking for C, COBOL, and fallback strategies."""

import logging
import re

import tree_sitter_c
from tree_sitter import Language, Parser
from llama_index.core.schema import Document, TextNode
from llama_index.core.node_parser import SentenceSplitter

logger = logging.getLogger(__name__)

# Max chunk size in chars — oversized chunks get split by fallback splitter
MAX_CHUNK_CHARS = 3000

# --- Tree-sitter C setup ---
C_LANGUAGE = Language(tree_sitter_c.language())
_c_parser = Parser(C_LANGUAGE)

# --- Fallback splitter ---
_fallback_splitter = SentenceSplitter(chunk_size=1500, chunk_overlap=200)


# ============================================================
# C Chunker (tree-sitter)
# ============================================================

def _extract_function_name(func_node) -> str:
    """Extract function name from a function_definition AST node."""
    for child in func_node.children:
        if child.type == "function_declarator":
            for sub in child.children:
                if sub.type == "identifier":
                    return sub.text.decode()
        # Handle pointer return types: int *func(...)
        if child.type == "pointer_declarator":
            for sub in child.children:
                if sub.type == "function_declarator":
                    for subsub in sub.children:
                        if subsub.type == "identifier":
                            return subsub.text.decode()
    return "unknown"


def _collect_top_level_nodes(root_node):
    """
    Walk AST root and yield (node_type, node) for each top-level declaration.
    Groups: function_definition, preproc_include, struct_specifier, etc.
    """
    for child in root_node.children:
        yield child


def chunk_c_file(doc: Document) -> list[TextNode]:
    """
    Chunk a C/header file using tree-sitter.
    Each function becomes its own chunk. Non-function top-level items
    are grouped into blocks so nothing is lost.
    """
    source = doc.text.encode("utf-8")
    tree = _c_parser.parse(source)
    root = tree.root_node

    nodes: list[TextNode] = []
    non_func_buffer: list[str] = []
    non_func_start_line: int | None = None
    non_func_end_line: int = 0

    for child in root.children:
        if child.type == "function_definition":
            # Flush non-function buffer first
            if non_func_buffer:
                nodes.append(_make_node(
                    text="\n".join(non_func_buffer),
                    doc=doc,
                    chunk_type="top_level",
                    line_start=non_func_start_line,
                    line_end=non_func_end_line,
                ))
                non_func_buffer = []
                non_func_start_line = None

            # Create function chunk
            func_name = _extract_function_name(child)
            func_text = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
            line_start = child.start_point[0] + 1
            line_end = child.end_point[0] + 1

            nodes.append(_make_node(
                text=func_text,
                doc=doc,
                chunk_type="function",
                function_name=func_name,
                line_start=line_start,
                line_end=line_end,
            ))
        else:
            # Accumulate non-function items
            text = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
            if text.strip():
                if non_func_start_line is None:
                    non_func_start_line = child.start_point[0] + 1
                non_func_end_line = child.end_point[0] + 1
                non_func_buffer.append(text)

    # Flush remaining non-function items
    if non_func_buffer:
        nodes.append(_make_node(
            text="\n".join(non_func_buffer),
            doc=doc,
            chunk_type="top_level",
            line_start=non_func_start_line,
            line_end=non_func_end_line,
        ))

    return nodes


# ============================================================
# COBOL Chunker (regex)
# ============================================================

# Matches DIVISION headers like "PROCEDURE DIVISION."
_DIVISION_RE = re.compile(r"^\s{0,6}\s*(\w[\w\s-]*DIVISION)\s*\.?\s*$", re.IGNORECASE | re.MULTILINE)
# Matches SECTION headers like "WORKING-STORAGE SECTION."
_SECTION_RE = re.compile(r"^\s{0,6}\s*(\w[\w\s-]*SECTION)\s*\.?\s*$", re.IGNORECASE | re.MULTILINE)
# Matches paragraph names: identifier at start of line (col 8-11) followed by period
_PARAGRAPH_RE = re.compile(r"^       ([A-Z0-9][\w-]*)\.\s*$", re.MULTILINE)


def chunk_cobol_file(doc: Document) -> list[TextNode]:
    """
    Chunk a COBOL file by DIVISION/SECTION/PARAGRAPH boundaries.
    Each section or paragraph becomes its own chunk.
    """
    text = doc.text
    lines = text.split("\n")

    # Find all boundary positions
    boundaries: list[tuple[int, str, str]] = []  # (line_idx, type, name)

    for i, line in enumerate(lines):
        div_match = _DIVISION_RE.match(line)
        if div_match:
            boundaries.append((i, "division", div_match.group(1).strip()))
            continue

        sec_match = _SECTION_RE.match(line)
        if sec_match:
            boundaries.append((i, "section", sec_match.group(1).strip()))
            continue

        para_match = _PARAGRAPH_RE.match(line)
        if para_match:
            boundaries.append((i, "paragraph", para_match.group(1).strip()))

    # If no boundaries found, treat whole file as one chunk
    if not boundaries:
        return [_make_node(
            text=text,
            doc=doc,
            chunk_type="file",
            line_start=1,
            line_end=len(lines),
        )]

    # Create chunks between boundaries
    nodes: list[TextNode] = []

    # Content before first boundary (if any)
    if boundaries[0][0] > 0:
        pre_text = "\n".join(lines[:boundaries[0][0]])
        if pre_text.strip():
            nodes.append(_make_node(
                text=pre_text,
                doc=doc,
                chunk_type="preamble",
                line_start=1,
                line_end=boundaries[0][0],
            ))

    for idx, (line_idx, btype, bname) in enumerate(boundaries):
        # Chunk extends from this boundary to the next (or end of file)
        end_idx = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(lines)
        chunk_text = "\n".join(lines[line_idx:end_idx])

        if chunk_text.strip():
            nodes.append(_make_node(
                text=chunk_text,
                doc=doc,
                chunk_type=btype,
                function_name=bname,
                line_start=line_idx + 1,
                line_end=end_idx,
            ))

    return nodes


# ============================================================
# Fallback Chunker (SentenceSplitter)
# ============================================================

def chunk_fallback(doc: Document) -> list[TextNode]:
    """
    Chunk file using LlamaIndex SentenceSplitter for Yacc, Lex, .def, etc.
    """
    base_nodes = _fallback_splitter.get_nodes_from_documents([doc])

    nodes: list[TextNode] = []
    for i, node in enumerate(base_nodes):
        # Estimate line numbers from character offsets
        text_before = doc.text[:doc.text.find(node.text[:50])] if node.text[:50] in doc.text else ""
        line_start = text_before.count("\n") + 1 if text_before else 1
        line_end = line_start + node.text.count("\n")

        node.metadata.update({
            "file_path": doc.metadata["file_path"],
            "file_extension": doc.metadata["file_extension"],
            "language": doc.metadata["language"],
            "chunk_type": "block",
            "line_start": line_start,
            "line_end": line_end,
            "chunk_index": i,
        })
        nodes.append(node)

    return nodes


# ============================================================
# Node constructor helper
# ============================================================

def _make_node(
    text: str,
    doc: Document,
    chunk_type: str,
    line_start: int | None = None,
    line_end: int | None = None,
    function_name: str | None = None,
) -> TextNode:
    """Create a TextNode with standard metadata."""
    metadata = {
        "file_path": doc.metadata["file_path"],
        "file_extension": doc.metadata["file_extension"],
        "language": doc.metadata["language"],
        "chunk_type": chunk_type,
        "line_start": line_start or 1,
        "line_end": line_end or 1,
    }
    if function_name:
        metadata["function_name"] = function_name

    return TextNode(
        text=text,
        metadata=metadata,
    )


# ============================================================
# Router
# ============================================================

# Languages that use the C tree-sitter chunker
_C_LANGUAGES = {"c", "c_header"}
# Languages that use the COBOL regex chunker
_COBOL_LANGUAGES = {"cobol", "cobol_copybook"}


def _split_oversized(nodes: list[TextNode]) -> list[TextNode]:
    """Split any chunks larger than MAX_CHUNK_CHARS using the fallback splitter."""
    result: list[TextNode] = []
    for node in nodes:
        if len(node.text) <= MAX_CHUNK_CHARS:
            result.append(node)
        else:
            # Create a temporary Document so SentenceSplitter can process it
            tmp_doc = Document(text=node.text, metadata=node.metadata.copy())
            sub_nodes = _fallback_splitter.get_nodes_from_documents([tmp_doc])
            base_line = node.metadata.get("line_start", 1)
            for i, sub in enumerate(sub_nodes):
                # Estimate line numbers within the sub-chunk
                sub.metadata.update(node.metadata)
                sub.metadata["chunk_type"] = f"{node.metadata.get('chunk_type', 'block')}_split"
                sub.metadata["chunk_index"] = i
                # Rough line estimate
                offset_lines = node.text[:node.text.find(sub.text[:40])].count("\n") if sub.text[:40] in node.text else 0
                sub.metadata["line_start"] = base_line + offset_lines
                sub.metadata["line_end"] = sub.metadata["line_start"] + sub.text.count("\n")
                result.append(sub)
    return result


def chunk_documents(documents: list[Document]) -> list[TextNode]:
    """
    Route documents to the appropriate chunker based on language.
    Returns all chunks as TextNode objects with metadata.
    Oversized chunks are automatically split.
    """
    all_nodes: list[TextNode] = []
    stats = {"c": 0, "cobol": 0, "fallback": 0, "errors": 0}

    for doc in documents:
        language = doc.metadata.get("language", "unknown")
        file_path = doc.metadata.get("file_path", "unknown")

        try:
            if language in _C_LANGUAGES:
                nodes = chunk_c_file(doc)
                stats["c"] += len(nodes)
            elif language in _COBOL_LANGUAGES:
                nodes = chunk_cobol_file(doc)
                stats["cobol"] += len(nodes)
            else:
                nodes = chunk_fallback(doc)
                stats["fallback"] += len(nodes)

            all_nodes.extend(nodes)
        except Exception as e:
            logger.error(f"Chunking failed for {file_path}: {e}")
            stats["errors"] += 1
            # Fallback: treat entire file as one chunk
            try:
                all_nodes.append(_make_node(
                    text=doc.text,
                    doc=doc,
                    chunk_type="file_fallback",
                    line_start=1,
                    line_end=doc.text.count("\n") + 1,
                ))
            except Exception:
                logger.error(f"Even fallback chunking failed for {file_path}")

    # Split oversized chunks
    before_split = len(all_nodes)
    all_nodes = _split_oversized(all_nodes)

    logger.info(
        f"Chunked into {len(all_nodes)} nodes "
        f"(C: {stats['c']}, COBOL: {stats['cobol']}, "
        f"fallback: {stats['fallback']}, errors: {stats['errors']}, "
        f"split: {len(all_nodes) - before_split + (before_split - len([n for n in all_nodes if '_split' not in n.metadata.get('chunk_type', '')]))} oversized→sub-chunks)"
    )

    return all_nodes
