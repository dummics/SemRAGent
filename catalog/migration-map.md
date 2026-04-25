# Workspace Docs Migration Map

This is a template for projects that want to gradually introduce the locator without moving files in bulk.

Recommended first pass:

- Mark authoritative docs as `canonical` or `runbook`.
- Mark old reviews, issue notes and archived docs as `historical`.
- Add project aliases in `.workspace-docs/topic-aliases.json`.
- Add expected retrieval queries in `.workspace-docs/eval-canonical-topics.json`.

Do not move or rewrite large documentation trees until the locator has reported duplicate and stale-document risks.
