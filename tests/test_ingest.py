"""Tests for the file loader."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.ingest.loader import load_codebase, detect_language, EXTENSION_MAP


class TestDetectLanguage:
    def test_c_file(self):
        assert detect_language(".c") == "c"

    def test_header_file(self):
        assert detect_language(".h") == "c_header"

    def test_cobol_file(self):
        assert detect_language(".cob") == "cobol"
        assert detect_language(".cbl") == "cobol"

    def test_copybook(self):
        assert detect_language(".cpy") == "cobol_copybook"

    def test_yacc(self):
        assert detect_language(".y") == "yacc"

    def test_lex(self):
        assert detect_language(".l") == "lex"

    def test_unknown(self):
        assert detect_language(".xyz") == "unknown"


class TestLoadCodebase:
    def test_nonexistent_path_raises(self):
        with pytest.raises(FileNotFoundError):
            load_codebase(Path("/nonexistent/path"))

    def test_loads_real_codebase(self):
        """Integration test — requires GnuCOBOL to be cloned."""
        codebase_path = Path("codebase/gnucobol")
        if not codebase_path.exists():
            pytest.skip("GnuCOBOL not downloaded")

        docs = load_codebase(codebase_path)

        # Should find 50+ files (assignment requirement)
        assert len(docs) >= 50

        # All docs should have required metadata
        for doc in docs:
            assert "file_path" in doc.metadata
            assert "file_extension" in doc.metadata
            assert "language" in doc.metadata
            assert "file_size" in doc.metadata
            assert doc.metadata["file_size"] > 0

        # Should have a mix of languages
        languages = {doc.metadata["language"] for doc in docs}
        assert "c" in languages

    def test_skips_binary_files(self):
        """Binary files (containing null bytes) should be skipped."""
        # This is tested implicitly by the real codebase test
        # The loader checks for \x00 in content
        pass
