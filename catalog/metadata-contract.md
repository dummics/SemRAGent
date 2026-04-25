---
id: workspace.agent-workflow.doc-locator.metadata-contract
title: Workspace Docs Locator Metadata Contract
status: canonical
doc_type: reference
repo_area: agent-workflow
authority: 1.0
owner: workspace
aliases:
  - doc locator metadata
  - locator frontmatter contract
canonical_for:
  - agent-workflow.doc-locator.metadata
review_status: current
---

# Workspace Docs Locator Metadata Contract

This MVP keeps Git + Markdown + manifest files as the source of truth. SQLite, FTS, Qdrant and model outputs are rebuildable indexes only.

## Status Values

Allowed status values:

- `canonical`
- `active`
- `runbook`
- `support`
- `generated`
- `historical`
- `deprecated`
- `archived`
- `inferred`

Authority order:

`canonical > runbook > active > generated > support > historical > deprecated/archived`

Default retrieval policy:

- `historical` is excluded unless `include_historical=true`.
- `deprecated` and `archived` are excluded by default.
- `generated` can support a result but should not beat a matching canonical doc.
- Missing frontmatter is allowed in MVP, but receives `status=inferred` unless a generated manifest or canonical navigation entry provides stronger authority.

## Recommended Frontmatter

```yaml
---
id: workspace.area.topic-name
title: Human Readable Title
status: canonical
doc_type: architecture
repo_area: server
component:
  - licensing
  - activation
authority: 1.0
owner: workspace
aliases:
  - activation flow
canonical_for:
  - server.license.activation
supersedes: []
replaced_by: null
last_reviewed: 2026-04-24
review_status: current
---
```

Do not apply this in bulk without a migration map. The first pass infers metadata and reports warnings.

