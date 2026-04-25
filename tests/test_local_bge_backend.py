from __future__ import annotations

import unittest
from pathlib import Path

from workspace_docs_mcp.config import load_config
from workspace_docs_mcp.local_bge_backend import BgeM3LocalBackend, ModelConfigurationError, lexical_weights_to_qdrant_sparse


class LocalBgeBackendContractTests(unittest.TestCase):
    def test_wrong_embedding_model_is_rejected_before_load(self) -> None:
        config = load_config(Path.cwd())
        config.data["models"]["embedding_model"] = "BAAI/bge-small-en-v1.5"

        with self.assertRaises(ModelConfigurationError):
            BgeM3LocalBackend.from_locator_config(config)

    def test_fallback_enabled_is_rejected_before_load(self) -> None:
        config = load_config(Path.cwd())
        config.data["models"]["allow_model_fallback"] = True

        with self.assertRaises(ModelConfigurationError):
            BgeM3LocalBackend.from_locator_config(config)

    def test_sparse_conversion_keeps_numeric_indices(self) -> None:
        sparse = lexical_weights_to_qdrant_sparse({9: 0.25, 2: 1.5})

        self.assertIsNotNone(sparse)
        self.assertEqual(sparse.indices, [2, 9])
        self.assertEqual(sparse.values, [1.5, 0.25])


if __name__ == "__main__":
    unittest.main()

