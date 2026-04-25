from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


VALID_STATUSES = {"canonical", "active", "runbook", "support", "generated", "historical", "deprecated", "archived", "inferred"}


@dataclass
class Document:
    document_id: str
    path: str
    title: str
    status: str
    doc_type: str
    repo_area: str
    authority: float
    owner: str = "licensing-framework"
    aliases: list[str] = field(default_factory=list)
    canonical_for: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    replaced_by: str | None = None
    last_reviewed: str | None = None
    review_status: str | None = None
    content_hash: str = ""
    git_commit: str = ""
    last_modified: str = ""
    frontmatter: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    path: str
    title: str
    status: str
    doc_type: str
    repo_area: str
    authority: float
    heading_path: list[str]
    anchor: str
    line_start: int
    line_end: int
    text: str
    text_for_embedding: str
    token_estimate: int
    content_hash: str
    git_commit: str
    last_modified: str
    chunker_version: str
    embedding_model: str
    aliases: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    path: str
    title: str
    status: str
    doc_type: str
    repo_area: str
    authority: float
    line_start: int
    line_end: int
    heading_path: list[str]
    anchor: str
    snippet: str
    score: float
    dense_score: float = 0.0
    sparse_score: float = 0.0
    lexical_score: float = 0.0
    exact_score: float = 0.0
    authority_score: float = 0.0
    route_match_score: float = 0.0
    freshness_score: float = 0.0
    reranker_score: float | None = None
    why: list[str] = field(default_factory=list)
    policy_adjustments: list[str] = field(default_factory=list)

    @property
    def citation(self) -> str:
        return f"{self.path}#L{self.line_start}-L{self.line_end}"

