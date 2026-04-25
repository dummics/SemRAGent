# MVP Improvement Backlog

## P0

- Add first-class glossary/entity candidate generation for `domain-definitions.json`, `glossary.yml`, `terms.md`, and `standard-definitions.md`.
- Add lightweight query intent detection: `definition`, `runbook`, `decision`, `troubleshooting`, `architecture`, `api`, `symbol`.
- Add adapter manifest schema under `.workspace-docs/adapter.yml`.
- Add debug output for misses: searched sources, matched aliases, excluded docs, index state, and recommended fix.

## P1

- Add project-neutral eval runner with required metrics: recall@1/3/5, citation validity, canonical hit rate, historical false-win rate, exact-symbol hit rate.
- Add background indexing health budget: debounce, max delta, stale lock detection, process liveness check, and optional load check.
- Add duplicate and stale-document reporting.
- Add structured source types: `markdown`, `glossary`, `adr`, `openapi`, `manifest`, `generated_index`.

## P2

- Add optional OpenAPI route extraction.
- Add optional ADR/decision parser.
- Add adapter examples for a Python repo, a Node repo, and a .NET repo.
- Add JSON schema files for config, aliases, and eval cases.
- Add install docs for Codex, Claude Desktop, and generic MCP clients.
