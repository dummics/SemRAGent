# GPT Pro Review Brief: Workspace Docs MCP

## Context

`workspace-docs-mcp` is a local-first, read-only MCP server that helps coding agents locate authoritative documentation in a workspace.

It is not intended to generate answers from documents. The MVP goal is:

> Given a topic/query/symbol/path, return where the correct documentation is, with path, heading, line range, status, confidence, ranking signals, citation, and short explanation.

## Current Architecture

- Source of truth: Git-tracked Markdown and project manifests.
- Deterministic catalog: SQLite at `.rag/catalog.sqlite`.
- Vector/hybrid cache: Qdrant local collections.
- Embedding backend: `FlagEmbedding.BGEM3FlagModel`.
- Embedding model: `BAAI/bge-m3`.
- Reranker backend: `FlagEmbedding.FlagReranker`.
- Reranker model: `BAAI/bge-reranker-v2-m3`.
- MCP: read-only tools only.
- Agent default flow: `find_docs` / `locate_topic` -> `open_doc`.

## Current MCP Tools

- `find_docs`
- `locate_topic`
- `open_doc`
- `search_exact`
- `list_canonical`
- `doc_neighbors`
- `explain_result`
- `index_status`

`search_exact` is intentionally not a fallback for semantic search failure. It is only for explicit symbols, paths, config keys, route IDs, error codes, and manifest names.

## Current Strengths

- Local-only model execution.
- No fallback to alternate models.
- Qdrant is a rebuildable cache, not source of truth.
- SQLite catalog remains inspectable.
- Results include citations and line ranges.
- Scores are normalized `0..1` with three decimals.
- Search output is compact by default, with `verbosity=full` and `explain_result` for debugging.
- Background indexing can start automatically with lock/debounce/max-change guardrails.
- Licensing Framework is included only as an example adapter/fixture.

## Requested Review

Please review this repository as an MVP for a generic agent-facing documentation locator.

Focus on:

- Whether the core abstractions are project-neutral enough.
- How to add first-class glossary/entity handling.
- How to improve intent detection without overbuilding.
- How to make hybrid retrieval more deterministic.
- How to make debug output explain "why nothing was found".
- How to make adapters simple for arbitrary repos.
- How to keep MCP usage seamless and token-efficient.
- How to harden background indexing without making the MCP unsafe.

## Important Non-Goals

- No generative RAG chatbot.
- No cloud dependency as a base requirement.
- No MCP shell execution.
- No write tools in the MCP.
- No vector DB as source of truth.
- No enterprise platform.

## Seed Recommendation From Prior Agent

The prior test agent recommended making this a generic `workspace-docs-mcp`, with:

- Generic core concepts: workspace, sources, authority, areas, entities, query intents.
- Per-project adapter manifest.
- Hybrid retrieval order: intent detection, entity/alias resolution, structured manifest lookup, authority boost, BM25, vector, rerank, explanation.
- First-class glossaries for definition/naming/domain queries.
- Debug mode explaining misses, exclusions, stale index state, and recommended fixes.
- Licensing Framework as fixture/example, not core.

## Questions For GPT Pro

1. What is the smallest set of changes needed to make this MVP reliable across different codebases?
2. Should glossary/entity lookup happen before SQLite FTS, or as a separate candidate generator merged into ranking?
3. What should the adapter manifest schema be?
4. Which current LF-specific assumptions are still leaking into core?
5. What retrieval eval cases should be mandatory before calling this MVP final?
6. How should background indexing behave when the workspace is large or the machine is under load?
7. What should be removed from the MVP to keep it focused?
