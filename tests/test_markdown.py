from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workspace_docs_mcp.config import load_config
from workspace_docs_mcp.markdown import parse_document, slugify


class MarkdownParserTests(unittest.TestCase):
    def test_frontmatter_heading_line_ranges_and_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc_path = root / "docs" / "server" / "sample.md"
            doc_path.parent.mkdir(parents=True)
            doc_path.write_text(
                "---\n"
                "id: workspace.server.sample\n"
                "title: Sample Doc\n"
                "status: canonical\n"
                "doc_type: architecture\n"
                "repo_area: server\n"
                "aliases:\n"
                "  - sample alias\n"
                "---\n"
                "# Sample Doc\n"
                "\n"
                "Intro.\n"
                "\n"
                "## Server Validation\n"
                "Body line.\n",
                encoding="utf-8",
            )
            config = load_config(root)
            doc, chunks, _links = parse_document(doc_path, config, {"docs/server/sample.md"}, {}, "abc123")
            self.assertEqual(doc.status, "canonical")
            self.assertEqual(doc.repo_area, "server")
            self.assertTrue(any(c.anchor == "#server-validation" for c in chunks))
            validation = next(c for c in chunks if c.anchor == "#server-validation")
            self.assertEqual(validation.line_start, 14)
            self.assertEqual(validation.line_end, 15)

    def test_slugify_github_style_anchor(self) -> None:
        self.assertEqual(slugify("Server validation (`V3`)"), "#server-validation-v3")


if __name__ == "__main__":
    unittest.main()

