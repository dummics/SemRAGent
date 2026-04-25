# Workspace Docs MCP Usage Procedure

Treat `workspace-docs-mcp` as the first stop for finding documentation.

## Default Agent Flow

1. Call `find_docs`.
2. If a heading-level citation is better, call `locate_topic`.
3. Open only returned citations with `open_doc`.

That is the normal path. Do not add a manual status/check/indexing prelude to every task.

## Exact Search Boundary

Use `search_exact` only when the owner/query explicitly gives a symbol, path, config key, error code, route id, or manifest name.

Do not use `search_exact`, `rg`, broad shell search, generated-index spelunking, or manual directory scans as fallback when semantic search is empty, stale, or blocked.

If search returns `background_index_started` or `background_index_running`, wait briefly and retry the same semantic search.
If `index_status.state` remains `blocked`, report the blocker to the owner/operator.

## Interpretation

- `high`: safe to open and use the cited doc/section.
- `medium`: plausible; inspect the cited section before acting.
- `low`: query is broad, signals disagree, or index/source metadata needs improvement.

Scores are normalized `0..1` with three decimals. Use `explain_result` when debugging ranking.
