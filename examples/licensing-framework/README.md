# Licensing Framework Example Adapter

This folder keeps the real project-specific configuration that motivated SemRAGent.

It is intentionally an example fixture, not core logic.

Files:

- `locator.config.yml`: source roots, model settings, Qdrant collection names, and policy weights used by Licensing Framework.
- `topic-aliases.json`: curated topic aliases for known canonical docs.
- `expected-queries.json`: targeted retrieval expectations.

To use in a Licensing Framework checkout, copy/adapt these files into `.workspace-docs/`.
