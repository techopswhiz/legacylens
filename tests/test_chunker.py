"""Tests for the chunking system."""

import pytest
from llama_index.core.schema import Document

from app.ingest.chunker import (
    chunk_c_file,
    chunk_cobol_file,
    chunk_fallback,
    chunk_documents,
)


# --- Fixtures ---

def _make_doc(text: str, language: str = "c", ext: str = ".c") -> Document:
    return Document(
        text=text,
        metadata={
            "file_path": f"test/sample{ext}",
            "file_extension": ext,
            "language": language,
            "file_size": len(text),
        },
    )


# --- C Chunker Tests ---

class TestCChunker:
    def test_single_function(self):
        code = "int main(int argc, char **argv) {\n    return 0;\n}\n"
        doc = _make_doc(code)
        nodes = chunk_c_file(doc)
        assert len(nodes) >= 1
        func_nodes = [n for n in nodes if n.metadata["chunk_type"] == "function"]
        assert len(func_nodes) == 1
        assert func_nodes[0].metadata["function_name"] == "main"

    def test_multiple_functions(self):
        code = (
            "void foo() { return; }\n"
            "int bar(int x) { return x + 1; }\n"
            "char *baz() { return NULL; }\n"
        )
        doc = _make_doc(code)
        nodes = chunk_c_file(doc)
        func_nodes = [n for n in nodes if n.metadata["chunk_type"] == "function"]
        names = [n.metadata["function_name"] for n in func_nodes]
        assert "foo" in names
        assert "bar" in names
        assert "baz" in names

    def test_preserves_non_function_code(self):
        code = (
            "#include <stdio.h>\n"
            "#define MAX 100\n"
            "int global_var = 42;\n"
            "void func() { return; }\n"
        )
        doc = _make_doc(code)
        nodes = chunk_c_file(doc)
        # Should have both function and top_level chunks
        types = {n.metadata["chunk_type"] for n in nodes}
        assert "function" in types
        assert "top_level" in types

    def test_line_numbers(self):
        code = (
            "// line 1\n"
            "// line 2\n"
            "void func() {\n"  # line 3
            "    return;\n"     # line 4
            "}\n"               # line 5
        )
        doc = _make_doc(code)
        nodes = chunk_c_file(doc)
        func_nodes = [n for n in nodes if n.metadata["chunk_type"] == "function"]
        assert len(func_nodes) == 1
        assert func_nodes[0].metadata["line_start"] == 3
        assert func_nodes[0].metadata["line_end"] == 5

    def test_empty_file(self):
        doc = _make_doc("")
        nodes = chunk_c_file(doc)
        assert len(nodes) == 0

    def test_header_file(self):
        code = (
            "#ifndef FOO_H\n"
            "#define FOO_H\n"
            "typedef struct { int x; } Point;\n"
            "void init_point(Point *p);\n"
            "#endif\n"
        )
        doc = _make_doc(code, language="c_header", ext=".h")
        nodes = chunk_c_file(doc)
        assert len(nodes) >= 1


# --- COBOL Chunker Tests ---

class TestCOBOLChunker:
    def test_division_detection(self):
        code = (
            "       IDENTIFICATION DIVISION.\n"
            "       PROGRAM-ID. HELLO.\n"
            "       PROCEDURE DIVISION.\n"
            "           DISPLAY 'HELLO'.\n"
            "           STOP RUN.\n"
        )
        doc = _make_doc(code, language="cobol", ext=".cob")
        nodes = chunk_cobol_file(doc)
        assert len(nodes) >= 2
        types = [n.metadata["chunk_type"] for n in nodes]
        assert "division" in types

    def test_section_detection(self):
        code = (
            "       DATA DIVISION.\n"
            "       WORKING-STORAGE SECTION.\n"
            "       01 WS-VAR PIC X(10).\n"
            "       FILE SECTION.\n"
            "       FD INPUT-FILE.\n"
        )
        doc = _make_doc(code, language="cobol", ext=".cob")
        nodes = chunk_cobol_file(doc)
        assert len(nodes) >= 2

    def test_no_boundaries_returns_whole_file(self):
        code = "       SOME RANDOM COBOL TEXT.\n"
        doc = _make_doc(code, language="cobol", ext=".cob")
        nodes = chunk_cobol_file(doc)
        assert len(nodes) == 1
        assert nodes[0].metadata["chunk_type"] == "file"


# --- Fallback Chunker Tests ---

class TestFallbackChunker:
    def test_small_file_single_chunk(self):
        code = "/* small file */\nrule: pattern { action };\n"
        doc = _make_doc(code, language="yacc", ext=".y")
        nodes = chunk_fallback(doc)
        assert len(nodes) >= 1
        assert nodes[0].metadata["chunk_type"] == "block"


# --- Router Tests ---

class TestRouter:
    def test_routes_c_to_c_chunker(self):
        docs = [_make_doc("void f() { return; }\n", language="c")]
        nodes = chunk_documents(docs)
        assert any(n.metadata.get("function_name") == "f" for n in nodes)

    def test_routes_cobol_to_cobol_chunker(self):
        code = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. TEST.\n"
        docs = [_make_doc(code, language="cobol", ext=".cob")]
        nodes = chunk_documents(docs)
        assert any(n.metadata.get("chunk_type") == "division" for n in nodes)

    def test_routes_unknown_to_fallback(self):
        docs = [_make_doc("some yacc content\n", language="yacc", ext=".y")]
        nodes = chunk_documents(docs)
        assert len(nodes) >= 1

    def test_all_nodes_have_required_metadata(self):
        docs = [
            _make_doc("void f() { return; }\n", language="c"),
            _make_doc("       IDENTIFICATION DIVISION.\n", language="cobol", ext=".cob"),
            _make_doc("fallback content here\n", language="lex", ext=".l"),
        ]
        nodes = chunk_documents(docs)
        for node in nodes:
            assert "file_path" in node.metadata
            assert "language" in node.metadata
            assert "chunk_type" in node.metadata
            assert "line_start" in node.metadata
            assert "line_end" in node.metadata
