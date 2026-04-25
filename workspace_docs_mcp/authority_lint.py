from __future__ import annotations

import json
from typing import Any

from .catalog import Catalog
from .config import LocatorConfig


def lint_authority(config: LocatorConfig) -> dict[str, Any]:
    catalog = Catalog(config)
    catalog.init()
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    with catalog.connect() as conn:
        for row in conn.execute("SELECT path,title FROM documents WHERE status='canonical' AND aliases_json='[]' ORDER BY path LIMIT 200"):
            warnings.append({"code": "canonical_without_aliases", "path": row["path"], "fix": "Add aliases frontmatter for likely user queries."})
        for row in conn.execute("SELECT path,title FROM documents WHERE status='canonical' AND canonical_for_json='[]' ORDER BY path LIMIT 200"):
            warnings.append({"code": "canonical_without_canonical_for", "path": row["path"], "fix": "Add canonical_for frontmatter if this doc owns a topic."})
        canonical_for: dict[str, list[str]] = {}
        for row in conn.execute("SELECT path,canonical_for_json FROM documents WHERE status='canonical'"):
            for topic in json.loads(row["canonical_for_json"] or "[]"):
                canonical_for.setdefault(str(topic), []).append(str(row["path"]))
        for topic, paths in canonical_for.items():
            if len(paths) > 1:
                failures.append({"code": "duplicate_canonical_for", "topic": topic, "paths": paths, "fix": "Keep one canonical owner or split topic aliases."})
        for row in conn.execute("SELECT path,title FROM documents WHERE status='historical' AND supersedes_json='[]' AND replaced_by IS NULL ORDER BY path LIMIT 200"):
            warnings.append({"code": "historical_without_supersedes_or_replaced_by", "path": row["path"], "fix": "Add supersedes/replaced_by metadata."})
        for row in conn.execute("SELECT path,title FROM documents WHERE status='inferred' ORDER BY path LIMIT 200"):
            warnings.append({"code": "inferred_status", "path": row["path"], "fix": "Add frontmatter status/doc_type/repo_area."})
        for row in conn.execute("SELECT title, COUNT(*) count, GROUP_CONCAT(path) paths FROM documents GROUP BY lower(title) HAVING count > 1 LIMIT 100"):
            warnings.append({"code": "duplicate_title", "title": row["title"], "paths": str(row["paths"]).split(","), "fix": "Clarify titles or aliases."})
        for row in conn.execute("SELECT alias, COUNT(DISTINCT path) count, GROUP_CONCAT(DISTINCT path) paths FROM aliases GROUP BY lower(alias) HAVING count > 1 LIMIT 100"):
            warnings.append({"code": "duplicate_alias", "alias": row["alias"], "paths": str(row["paths"]).split(","), "fix": "Disambiguate aliases or adjust weights."})
        for row in conn.execute("SELECT term,source_path FROM entities WHERE canonical_docs_json='[]' LIMIT 200"):
            warnings.append({"code": "glossary_term_without_canonical_docs", "term": row["term"], "path": row["source_path"], "fix": "Link glossary term to canonical docs."})
    return {"ok": not failures, "failures": failures, "warnings": warnings, "summary": {"failures": len(failures), "warnings": len(warnings)}}
