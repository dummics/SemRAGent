from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ModelConfigurationError(RuntimeError):
    """Raised when the configured model/backend violates the locator contract."""


class ModelLoadError(RuntimeError):
    """Raised when a required local model cannot be loaded or validated."""


@dataclass(frozen=True)
class BgeLocalConfig:
    embedding_backend: str = "flagembedding_bgem3"
    embedding_model: str = "BAAI/bge-m3"
    reranker_backend: str = "flagembedding_reranker"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    allow_model_fallback: bool = False
    require_exact_model_names: bool = True
    require_embedding_dimension: int = 1024
    require_reranker: bool = True
    use_fp16: str | bool = "auto"
    query_max_length: int = 512
    passage_max_length: int = 2048
    max_model_length: int = 8192

    @classmethod
    def from_locator_config(cls, config: Any) -> "BgeLocalConfig":
        models = config.data.get("models", {})
        return cls(
            embedding_backend=str(models.get("embedding_backend", cls.embedding_backend)),
            embedding_model=str(models.get("embedding_model", cls.embedding_model)),
            reranker_backend=str(models.get("reranker_backend", cls.reranker_backend)),
            reranker_model=str(models.get("reranker_model", cls.reranker_model)),
            allow_model_fallback=bool(models.get("allow_model_fallback", cls.allow_model_fallback)),
            require_exact_model_names=bool(models.get("require_exact_model_names", cls.require_exact_model_names)),
            require_embedding_dimension=int(models.get("require_embedding_dimension", cls.require_embedding_dimension)),
            require_reranker=bool(models.get("require_reranker", cls.require_reranker)),
            use_fp16=models.get("use_fp16", cls.use_fp16),
            query_max_length=int(models.get("query_max_length", cls.query_max_length)),
            passage_max_length=int(models.get("passage_max_length", cls.passage_max_length)),
            max_model_length=int(models.get("max_model_length", cls.max_model_length)),
        )


def _as_bool_fp16(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    if str(value).lower() != "auto":
        return str(value).lower() in {"1", "true", "yes", "on"}
    try:
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _dense_list(value: Any) -> list[list[float]]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, list) and value and isinstance(value[0], (float, int)):
        return [[float(v) for v in value]]
    return [[float(v) for v in row] for row in value]


def lexical_weights_to_qdrant_sparse(lexical_weights: dict[int, float] | dict[str, float] | None):
    from qdrant_client.http import models  # type: ignore

    if not lexical_weights:
        return None
    pairs = sorted((int(index), float(value)) for index, value in lexical_weights.items() if float(value) != 0.0)
    if not pairs:
        return None
    return models.SparseVector(indices=[index for index, _ in pairs], values=[value for _, value in pairs])


class BgeM3LocalBackend:
    REQUIRED_EMBEDDING_MODEL = "BAAI/bge-m3"
    REQUIRED_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"

    def __init__(self, config: BgeLocalConfig):
        self.config = config
        self._validate_config()
        self.use_fp16 = _as_bool_fp16(config.use_fp16)
        self.embedding_model = None
        self.reranker = None

    @classmethod
    def from_locator_config(cls, locator_config: Any) -> "BgeM3LocalBackend":
        return cls(BgeLocalConfig.from_locator_config(locator_config))

    def _validate_config(self) -> None:
        if self.config.allow_model_fallback:
            raise ModelConfigurationError("Model fallback is forbidden for Workspace Docs Locator.")
        if self.config.embedding_backend != "flagembedding_bgem3":
            raise ModelConfigurationError(f"Embedding backend must be flagembedding_bgem3, got {self.config.embedding_backend}.")
        if self.config.reranker_backend != "flagembedding_reranker":
            raise ModelConfigurationError(f"Reranker backend must be flagembedding_reranker, got {self.config.reranker_backend}.")
        if self.config.require_exact_model_names and self.config.embedding_model != self.REQUIRED_EMBEDDING_MODEL:
            raise ModelConfigurationError(f"Embedding model must be exactly {self.REQUIRED_EMBEDDING_MODEL}, got {self.config.embedding_model}.")
        if self.config.require_exact_model_names and self.config.reranker_model != self.REQUIRED_RERANKER_MODEL:
            raise ModelConfigurationError(f"Reranker model must be exactly {self.REQUIRED_RERANKER_MODEL}, got {self.config.reranker_model}.")
        if self.config.require_embedding_dimension != 1024:
            raise ModelConfigurationError("BAAI/bge-m3 dense embedding dimension must be required as 1024.")

    def load_embedding_model(self):
        if self.embedding_model is not None:
            return self.embedding_model
        try:
            from FlagEmbedding import BGEM3FlagModel  # type: ignore

            self.embedding_model = BGEM3FlagModel(
                self.config.embedding_model,
                use_fp16=self.use_fp16,
            )
        except Exception as exc:
            raise ModelLoadError(
                f"Required embedding model {self.REQUIRED_EMBEDDING_MODEL} could not be loaded. No fallback model is allowed. {exc}"
            ) from exc
        self._smoke_embedding_model()
        return self.embedding_model

    def load_reranker(self):
        if self.reranker is not None:
            return self.reranker
        try:
            from FlagEmbedding import FlagReranker  # type: ignore

            self.reranker = FlagReranker(self.config.reranker_model, use_fp16=self.use_fp16)
        except Exception as exc:
            raise ModelLoadError(
                f"Required reranker model {self.REQUIRED_RERANKER_MODEL} could not be loaded. No fallback model is allowed. {exc}"
            ) from exc
        self._smoke_reranker()
        return self.reranker

    def _smoke_embedding_model(self) -> None:
        encoded = self.encode_passages(["dimension probe"], return_sparse=True)
        dense = encoded["dense"]
        if len(dense) != 1 or len(dense[0]) != self.config.require_embedding_dimension:
            raise ModelLoadError(
                f"BAAI/bge-m3 dense embedding dimension mismatch: expected {self.config.require_embedding_dimension}, got {len(dense[0]) if dense else 0}."
            )
        sparse = encoded.get("sparse") or []
        if not sparse or not sparse[0]:
            raise ModelLoadError("BAAI/bge-m3 did not return sparse lexical_weights. No fallback model is allowed.")

    def _smoke_reranker(self) -> None:
        scores = self.rerank_pairs(
            [
                ("server license activation", "License activation validates a client request on the server."),
                ("server license activation", "This document explains Blender material baking."),
            ],
            normalize=False,
        )
        if len(scores) != 2:
            raise ModelLoadError("BAAI/bge-reranker-v2-m3 did not return two smoke scores.")
        if float(scores[0]) <= float(scores[1]):
            raise ModelLoadError("BAAI/bge-reranker-v2-m3 smoke relevance ordering failed.")

    def _encode(self, texts: list[str], *, return_sparse: bool, max_length: int) -> dict[str, Any]:
        model = self.embedding_model
        if model is None:
            try:
                from FlagEmbedding import BGEM3FlagModel  # type: ignore

                model = BGEM3FlagModel(self.config.embedding_model, use_fp16=self.use_fp16)
                self.embedding_model = model
            except Exception as exc:
                raise ModelLoadError(
                    f"Required embedding model {self.REQUIRED_EMBEDDING_MODEL} could not be loaded. No fallback model is allowed. {exc}"
                ) from exc
        try:
            encoded = model.encode(
                texts,
                batch_size=8,
                max_length=max_length,
                return_dense=True,
                return_sparse=return_sparse,
                return_colbert_vecs=False,
            )
        except Exception as exc:
            raise ModelLoadError(f"BAAI/bge-m3 encode failed. No fallback model is allowed. {exc}") from exc
        dense = _dense_list(encoded.get("dense_vecs"))
        for vector in dense:
            if len(vector) != self.config.require_embedding_dimension:
                raise ModelLoadError(
                    f"BAAI/bge-m3 dense embedding dimension mismatch: expected {self.config.require_embedding_dimension}, got {len(vector)}."
                )
        lexical = encoded.get("lexical_weights") if return_sparse else None
        if return_sparse and lexical is None:
            raise ModelLoadError("BAAI/bge-m3 did not return lexical_weights. No fallback model is allowed.")
        return {"dense": dense, "sparse": lexical or []}

    def encode_queries(self, queries: list[str], return_sparse: bool = True) -> dict[str, Any]:
        return self._encode(queries, return_sparse=return_sparse, max_length=self.config.query_max_length)

    def encode_passages(self, passages: list[str], return_sparse: bool = True) -> dict[str, Any]:
        return self._encode(passages, return_sparse=return_sparse, max_length=self.config.passage_max_length)

    def rerank_pairs(self, pairs: list[tuple[str, str]] | list[list[str]], normalize: bool = True) -> list[float]:
        reranker = self.load_reranker()
        try:
            scores = reranker.compute_score(pairs, normalize=normalize)
        except TypeError:
            scores = reranker.compute_score(pairs)
        except Exception as exc:
            raise ModelLoadError(f"BAAI/bge-reranker-v2-m3 rerank failed. No fallback model is allowed. {exc}") from exc
        if not isinstance(scores, list):
            if hasattr(scores, "tolist"):
                scores = scores.tolist()
            else:
                scores = list(scores)
        return [float(score) for score in scores]

    def rerank_candidates(self, query: str, candidates: list[dict[str, Any]], text_key: str = "text_for_rerank") -> list[dict[str, Any]]:
        pairs = [(query, str(candidate.get(text_key, ""))) for candidate in candidates]
        scores = self.rerank_pairs(pairs, normalize=True)
        out: list[dict[str, Any]] = []
        for candidate, score in zip(candidates, scores):
            updated = dict(candidate)
            updated["reranker_score"] = score
            out.append(updated)
        return sorted(out, key=lambda item: item["reranker_score"], reverse=True)

