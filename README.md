---
title: Workspace Docs MCP
status: active
---

# Workspace Docs MCP

Generic local, read-only MCP server for locating authoritative documentation in a project workspace.

It is not a chat RAG system. Its job is narrower:

> Given a query, topic, symbol, or path, return the right document/section with citation, status, confidence, ranking signals, and a short explanation.

## Principles

- Git + Markdown + project manifests are the source of truth.
- SQLite is the deterministic catalog.
- Qdrant is a rebuildable vector/sparse cache.
- Embeddings are local `BAAI/bge-m3` via `FlagEmbedding.BGEM3FlagModel`.
- Reranking is local `BAAI/bge-reranker-v2-m3` via `FlagEmbedding.FlagReranker`.
- No fallback to alternate models.
- MCP tools are read-only.
- Agents should use semantic search first: `find_docs` / `locate_topic` -> `open_doc`.

## MCP Tools

- `find_docs`: document-first semantic locator.
- `locate_topic`: section-first semantic locator.
- `open_doc`: open a returned citation/path.
- `search_exact`: exact lookup for explicit symbols, paths, config keys, route IDs, or manifest names only.
- `list_canonical`: list canonical/runbook docs by area/topic.
- `doc_neighbors`: links and related docs.
- `explain_result`: explain ranking for a query/path.
- `index_status`: compact readiness report.

Default search output is compact and token-efficient. Scores are normalized `0..1` with three decimals, for example `0.756`.
Use `verbosity=full` or `explain_result` for debugging.

## Install From Source

```powershell
cd "$env:USERPROFILE\.scriptsdum\workspace-docs-mcp"
python -m pip install -e .[vector,models,yaml]
```

For NVIDIA CUDA on Windows, install a CUDA PyTorch wheel before running model checks:

```powershell
python -m pip install --user --force-reinstall "torch==2.7.1" "torchvision==0.22.1" "torchaudio==2.7.1" --index-url https://download.pytorch.org/whl/cu128
python -m pip install --user "numpy==1.26.4" "setuptools>=80.9.0" "pillow>=10.3,<11"
```

## Project Configuration

Create `.workspace-docs/locator.config.yml` in the target workspace.

Start from:

```powershell
Copy-Item "$env:USERPROFILE\.scriptsdum\workspace-docs-mcp\catalog\locator.config.yml" ".workspace-docs\locator.config.yml"
```

Optional project files:

- `.workspace-docs/topic-aliases.json`
- `.workspace-docs/eval-canonical-topics.json`
- `.workspace-docs/canonical-map.yml`

The `examples/licensing-framework/` folder contains the real adapter that motivated the tool.

## Qdrant

```powershell
docker run -p 6333:6333 -v ${PWD}/.rag/qdrant:/qdrant/storage qdrant/qdrant
```

## CLI

From the target workspace:

```powershell
workspace-docs models doctor
workspace-docs index build
workspace-docs search "where is the API authentication runbook?"
workspace-docs mcp
```

Or from the source checkout without installing:

```powershell
$tool = "$env:USERPROFILE\.scriptsdum\workspace-docs-mcp"
$env:PYTHONPATH = $tool
python -m workspace_docs_mcp.cli --root "C:\path\to\workspace" models doctor
python -m workspace_docs_mcp.cli --root "C:\path\to\workspace" index build
python -m workspace_docs_mcp.cli --root "C:\path\to\workspace" mcp
```

## MCP Config

Example Codex config:

```toml
[mcp_servers.workspaceDocs]
command = "cmd"
args = ["/c", "C:\\Users\\domix\\.scriptsdum\\workspace-docs-mcp\\bin\\workspace-docs-mcp.cmd", "-Root", "C:\\path\\to\\workspace"]
enabled = true
startup_timeout_sec = 120
tool_timeout_sec = 300
```

Expected server name: `workspace-docs-mcp`.

## Agent Pattern

Normal flow:

1. Call `find_docs` for "where is the doc for X?"
2. Call `locate_topic` when a section-level citation is better.
3. Call `open_doc` only for a returned citation/path.

Do not use `search_exact`, shell search, or manual generated-index reading as fallback after semantic search fails, is stale, or is blocked.
If `index_status.state` is `blocked` and `background_index_started/running`, wait briefly and retry the same semantic search.
If it remains blocked, report the blocker to the owner/operator.

## GPT Pro Review Package

This repo includes:

- `docs/gpt-pro-review-brief.md`
- `docs/mvp-improvement-backlog.md`
- `examples/licensing-framework/`

Use these for external review of the MVP architecture and next improvements.
