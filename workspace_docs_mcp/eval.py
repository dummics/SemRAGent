from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import Catalog
from .config import LocatorConfig
from .search import Retriever


def eval_candidates_path(config: LocatorConfig) -> Path:
    return config.root / ".workspace-docs" / "eval-candidates.json"


def eval_golden_path(config: LocatorConfig) -> Path:
    return config.root / ".workspace-docs" / "eval-golden.json"


def eval_report_paths(config: LocatorConfig) -> tuple[Path, Path]:
    folder = config.root / ".rag" / "eval"
    return folder / "latest.json", folder / "latest.md"


def bootstrap_eval(config: LocatorConfig) -> dict[str, Any]:
    catalog = Catalog(config)
    catalog.init()
    cases: list[dict[str, Any]] = []
    with catalog.connect() as conn:
        for row in conn.execute("SELECT path,title,status,repo_area,aliases_json,canonical_for_json FROM documents WHERE status IN ('canonical','runbook') ORDER BY authority DESC,path LIMIT 100"):
            aliases = json.loads(row["aliases_json"] or "[]")
            canonical_for = json.loads(row["canonical_for_json"] or "[]")
            query = aliases[0] if aliases else canonical_for[0] if canonical_for else row["title"]
            cases.append({"id": f"doc-{len(cases)+1:03d}", "query": query, "tool": "find_docs", "candidate_expected_docs": [row["path"]], "expected_status": row["status"], "tags": ["candidate", row["repo_area"], row["status"]]})
        for row in conn.execute("SELECT term,source_path,canonical_docs_json FROM entities ORDER BY authority DESC,term LIMIT 100"):
            expected = json.loads(row["canonical_docs_json"] or "[]") or [row["source_path"]]
            cases.append({"id": f"entity-{len(cases)+1:03d}", "query": f"definition of {row['term']}", "tool": "locate_topic", "candidate_expected_docs": expected, "tags": ["candidate", "entity"]})
        for row in conn.execute("SELECT symbol,path FROM code_symbols ORDER BY path LIMIT 100"):
            cases.append({"id": f"symbol-{len(cases)+1:03d}", "query": row["symbol"], "tool": "search_exact", "candidate_expected_docs": [row["path"]], "tags": ["candidate", "exact", "symbol"]})
    path = eval_candidates_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "cases": cases}, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(path), "cases": len(cases), "note": "Candidates are not golden assertions until reviewed."}


def run_eval(config: LocatorConfig, rerank: bool = True) -> dict[str, Any]:
    path = eval_golden_path(config)
    if not path.exists():
        return {"ok": False, "error": "eval-golden.json not found", "owner_action": {"summary": "Bootstrap candidates, review them, then create eval-golden.json.", "commands": ["semragent eval bootstrap"], "safe_for_agent": True}}
    data = json.loads(path.read_text(encoding="utf-8"))
    retriever = Retriever(config)
    cases = []
    metrics = {"doc_recall@1": 0, "doc_recall@3": 0, "doc_recall@5": 0, "citation_validity": 0, "exact_symbol_hit@5": 0, "historical_false_win_rate": 0, "generated_false_win_rate": 0, "deprecated_return_rate": 0}
    total = 0
    for case in data.get("cases", []):
        total += 1
        tool = case.get("tool", "find_docs")
        if tool == "search_exact":
            result = retriever.exact(case["query"], max_results=5)
            top = result.get("results", [])
            paths = [item.get("path") for item in top]
            confidence = result.get("confidence")
        else:
            result = retriever.search(case["query"], max_results=5, rerank=rerank, mode="documents" if tool == "find_docs" else "sections")
            top = result.get("results", [])
            paths = [item.get("path") for item in top]
            confidence = result.get("confidence")
        expected = case.get("expected_docs", [])
        rank = next((idx + 1 for idx, actual in enumerate(paths) if actual in expected), None)
        if rank == 1:
            metrics["doc_recall@1"] += 1
        if rank and rank <= 3:
            metrics["doc_recall@3"] += 1
        if rank and rank <= 5:
            metrics["doc_recall@5"] += 1
        if tool == "search_exact" and rank and rank <= 5:
            metrics["exact_symbol_hit@5"] += 1
        if top and top[0].get("citation") or (top and tool == "search_exact"):
            metrics["citation_validity"] += 1
        if top and top[0].get("status") == "historical":
            metrics["historical_false_win_rate"] += 1
        if top and top[0].get("status") == "generated":
            metrics["generated_false_win_rate"] += 1
        if any(item.get("status") == "deprecated" for item in top):
            metrics["deprecated_return_rate"] += 1
        cases.append({"id": case.get("id"), "query": case.get("query"), "pass": bool(rank and rank <= 3), "expected": expected, "actual_top_paths": paths[:5], "confidence": confidence, "failure_reason": None if rank and rank <= 3 else "expected doc not in top 3", "suggested_fix": suggested_fix(rank, top)})
    normalized = {name: round(value / total, 3) if total else 0.0 for name, value in metrics.items()}
    report = {"ok": all(item["pass"] for item in cases), "total": total, "metrics": normalized, "cases": cases}
    write_report(config, report)
    return report


def report_eval(config: LocatorConfig) -> dict[str, Any]:
    json_path, md_path = eval_report_paths(config)
    return {"ok": json_path.exists(), "json": str(json_path), "markdown": str(md_path), "report": json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else None}


def write_report(config: LocatorConfig, report: dict[str, Any]) -> None:
    json_path, md_path = eval_report_paths(config)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# SemRAGent Eval Report", "", f"Total: {report['total']}", "", "## Metrics"]
    for key, value in report["metrics"].items():
        lines.append(f"- {key}: {value:.3f}")
    lines.extend(["", "## Failures"])
    for case in report["cases"]:
        if not case["pass"]:
            lines.append(f"- {case['id']}: {case['query']} -> {case['failure_reason']} ({case['suggested_fix']})")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def suggested_fix(rank: int | None, top: list[dict[str, Any]]) -> str:
    if not top:
        return "rebuild index or add alias/glossary entity"
    status = top[0].get("status")
    if status in {"historical", "generated", "support"}:
        return "adjust authority metadata or add canonical route"
    if not rank:
        return "add alias, glossary entity, route, or expected canonical metadata"
    return "review confidence calibration"
