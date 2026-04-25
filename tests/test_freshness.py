from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workspace_docs_mcp.config import load_config
from workspace_docs_mcp.freshness import IndexFreshnessService
from workspace_docs_mcp.search import score


class IndexFreshnessTests(unittest.TestCase):
    def test_scores_keep_three_decimals(self) -> None:
        self.assertEqual(score(0.7556), 0.756)
        self.assertEqual(score(1.234), 1.0)

    def test_auto_index_disabled_skips_worker(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            (root / "project.json").write_text("{}", encoding="utf-8")
            (root / "catalog").mkdir()
            (root / "catalog" / "bootstrap.json").write_text("{}", encoding="utf-8")
            config = load_config(root)
            config.data["auto_index"]["enabled"] = False

            result = IndexFreshnessService(config).maybe_start_background_index("usable_stale", ["docs/a.md"], True)

            self.assertEqual(result["state"], "skipped")
            self.assertEqual(result["reason"], "auto_index_disabled")

    def test_auto_index_skips_large_delta(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            (root / "project.json").write_text("{}", encoding="utf-8")
            (root / "catalog").mkdir()
            (root / "catalog" / "bootstrap.json").write_text("{}", encoding="utf-8")
            config = load_config(root)
            config.data["auto_index"]["max_changed_files"] = 1

            result = IndexFreshnessService(config).maybe_start_background_index("usable_stale", ["docs/a.md", "docs/b.md"], True)

            self.assertEqual(result["state"], "skipped")
            self.assertEqual(result["reason"], "too_many_changed_files")


if __name__ == "__main__":
    unittest.main()

