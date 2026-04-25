# Workspace Docs MCP Tool Contract

All tools are read-only. All paths are workspace-relative unless explicitly returned as a citation.

## `find_docs`

Document-first semantic locator. Use for "where is the doc for X?" It preflights index freshness and returns `search_mode=blocked` plus `owner_action` instead of silently falling back when the semantic index is unavailable.

## `locate_topic`

Section-first semantic locator. Use when a heading-level citation is more useful. It uses section chunks first.

## `open_doc`

Open a safe catalog-known document slice by path, heading, or line range. Blocks traversal outside the workspace and supports bounded `max_chars` output.

## `search_exact`

Exact lookup for explicit symbols, paths, config keys, route IDs, error codes, and manifest names.

This is not a fallback for semantic search failure.

## `list_canonical`

List canonical/runbook docs by area or topic.

## `doc_neighbors`

Show links and related docs for one path.

## `explain_result`

Explain ranking signals, candidate counts, active filters, index state, policy adjustments, and safety for one query/path pair. `path` can be null for no-results diagnostics.

## `index_status`

Compact readiness report for SQLite, Qdrant, model config, freshness, and background indexing.
