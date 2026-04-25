from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workspace_docs_mcp.catalog import Catalog
from workspace_docs_mcp.config import load_config
from workspace_docs_mcp.search import Retriever


class CatalogSearchTests(unittest.TestCase):
    def test_exact_search_and_historical_filter(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            docs = root / "docs"
            (docs / "server").mkdir(parents=True)
            (docs / "archive").mkdir(parents=True)
            (root / "catalog").mkdir()
            (root / "project.json").write_text("{}", encoding="utf-8")
            (root / "catalog" / "bootstrap.json").write_text("{}", encoding="utf-8")
            (docs / "navigation.json").write_text('{"docs":[{"path":"server/canonical.md"}]}', encoding="utf-8")
            (docs / "server" / "canonical.md").write_text("# Canonical Activation\n\nLicenseActivationHandler lives here.\n", encoding="utf-8")
            (docs / "archive" / "old.md").write_text("# Old Activation\n\nLicenseActivationHandler old note.\n", encoding="utf-8")

            config = load_config(root)
            with patch("workspace_docs_mcp.catalog.VectorIndex.rebuild_from_sqlite", return_value={"enabled": False, "reason": "unit-test"}):
                Catalog(config).rebuild()
            retriever = Retriever(config)
            exact = retriever.exact("LicenseActivationHandler", max_results=10)
            paths = [r["path"] for r in exact["results"]]
            self.assertIn("docs/server/canonical.md", paths)
            self.assertNotIn("docs/archive/old.md", paths)

            exact_with_history = retriever.exact("LicenseActivationHandler", include_historical=True, max_results=10)
            historical_paths = [r["path"] for r in exact_with_history["results"]]
            self.assertIn("docs/archive/old.md", historical_paths)

    def test_open_blocks_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            (root / "project.json").write_text("{}", encoding="utf-8")
            (root / "catalog").mkdir()
            (root / "catalog" / "bootstrap.json").write_text("{}", encoding="utf-8")
            config = load_config(root)
            with self.assertRaises(ValueError):
                Retriever(config).open_doc("../outside.md")


if __name__ == "__main__":
    unittest.main()

