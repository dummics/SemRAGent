from __future__ import annotations

from dataclasses import dataclass

from .catalog import Catalog
from .config import LocatorConfig
from .local_bge_backend import BgeM3LocalBackend
from .vector import VectorIndex


@dataclass
class RuntimeContext:
    config: LocatorConfig
    _catalog: Catalog | None = None
    _backend: BgeM3LocalBackend | None = None
    _vector: VectorIndex | None = None
    _retriever: object | None = None

    @property
    def catalog(self) -> Catalog:
        if self._catalog is None:
            self._catalog = Catalog(self.config)
        return self._catalog

    @property
    def backend(self) -> BgeM3LocalBackend:
        if self._backend is None:
            self._backend = BgeM3LocalBackend.from_locator_config(self.config)
        return self._backend

    @property
    def vector(self) -> VectorIndex:
        if self._vector is None:
            self._vector = VectorIndex(self.config, backend=self.backend)
        return self._vector

    @property
    def retriever(self):
        if self._retriever is None:
            from .search import Retriever

            self._retriever = Retriever(self)
        return self._retriever

