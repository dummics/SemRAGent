from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workspace_docs_mcp.authority_lint import lint_authority
from workspace_docs_mcp.catalog import Catalog
from workspace_docs_mcp.cli import build_parser
from workspace_docs_mcp.config import load_config
from workspace_docs_mcp.eval import bootstrap_eval, run_eval
from workspace_docs_mcp.qdrant_cli import qdrant_status


class SemRAGentProductTests(unittest.TestCase):
    def test_cli_parser_has_semragent_commands(self) -> None:
        parser = build_parser()
        self.assertEqual(parser.prog, Path(parser.prog).name)
        args = parser.parse_args(["models", "fetch"])
        self.assertEqual(args.command, "models")
        self.assertEqual(args.models_command, "fetch")
        args = parser.parse_args(["qdrant", "status"])
        self.assertEqual(args.qdrant_command, "status")
        args = parser.parse_args(["eval", "bootstrap"])
        self.assertEqual(args.eval_command, "bootstrap")

    def test_pyproject_exposes_semragent_alias(self) -> None:
        text = Path("pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("semragent = \"workspace_docs_mcp.cli:main\"", text)
        self.assertIn("workspace-docs = \"workspace_docs_mcp.cli:main\"", text)

    def test_readme_brands_semragent(self) -> None:
        text = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("# SemRAGent", text)
        self.assertIn("Semantic RAG routing for coding agents", text)
        self.assertIn("docs/TRUST_CONTRACT.md", text)

    def test_qdrant_status_handles_unavailable_endpoint(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            config = load_config(Path(tmp))
            with patch("qdrant_client.QdrantClient", side_effect=RuntimeError("down")):
                result = qdrant_status(config)
            self.assertFalse(result["ok"])
            self.assertIn("semragent qdrant start", result["owner_action"]["commands"])

    def test_lint_authority_detects_missing_alias_and_duplicate_canonical_for(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            docs = root / "docs"
            docs.mkdir()
            (root / ".workspace-docs").mkdir()
            (root / ".workspace-docs" / "locator.config.yml").write_text("version: 1\n", encoding="utf-8")
            (docs / "a.md").write_text("---\nstatus: canonical\ncanonical_for:\n  - activation\n---\n# A\n", encoding="utf-8")
            (docs / "b.md").write_text("---\nstatus: canonical\ncanonical_for:\n  - activation\n---\n# B\n", encoding="utf-8")
            with patch("workspace_docs_mcp.catalog.VectorIndex.rebuild_from_sqlite", return_value={"enabled": False}):
                Catalog(load_config(root)).rebuild()
            result = lint_authority(load_config(root))
            self.assertFalse(result["ok"])
            self.assertTrue(any(item["code"] == "canonical_without_aliases" for item in result["warnings"]))
            self.assertTrue(any(item["code"] == "duplicate_canonical_for" for item in result["failures"]))

    def test_eval_bootstrap_and_run_metrics(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            docs = root / "docs"
            docs.mkdir()
            (root / ".workspace-docs").mkdir()
            (root / ".workspace-docs" / "locator.config.yml").write_text("version: 1\n", encoding="utf-8")
            (docs / "activation.md").write_text("---\nstatus: canonical\naliases:\n  - activation flow\n---\n# Activation\n\nServer activation flow.\n", encoding="utf-8")
            with patch("workspace_docs_mcp.catalog.VectorIndex.rebuild_from_sqlite", return_value={"enabled": False}):
                Catalog(load_config(root)).rebuild()
            config = load_config(root)
            boot = bootstrap_eval(config)
            self.assertTrue(Path(boot["path"]).exists())
            golden = root / ".workspace-docs" / "eval-golden.json"
            golden.write_text('{"cases":[{"id":"q1","query":"activation flow","tool":"find_docs","expected_docs":["docs/activation.md"]}]}', encoding="utf-8")
            with patch("workspace_docs_mcp.search.VectorIndex.search_chunks", return_value=[]), patch("workspace_docs_mcp.search.VectorIndex.search_documents", return_value=[]):
                report = run_eval(config, rerank=False)
            self.assertIn("doc_recall@1", report["metrics"])
            self.assertTrue((root / ".rag" / "eval" / "latest.json").exists())


if __name__ == "__main__":
    unittest.main()
