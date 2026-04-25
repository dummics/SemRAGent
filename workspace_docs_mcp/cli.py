from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .catalog import Catalog
from .config import load_config
from .local_bge_backend import ModelConfigurationError, ModelLoadError
from .search import Retriever


def find_workspace(start: Path) -> Path:
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / "project.json").exists() and (parent / "catalog" / "bootstrap.json").exists():
            return parent
    return current


def emit(obj: object) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workspace-docs", description="Workspace Docs local Doc Locator")
    parser.add_argument("--root", default=None, help="Workspace root")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--json", action="store_true")

    index = sub.add_parser("index")
    index_sub = index.add_subparsers(dest="index_command", required=True)
    index_sub.add_parser("build")
    index_sub.add_parser("update")

    catalog = sub.add_parser("catalog")
    catalog_sub = catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_sub.add_parser("stats")
    doc = catalog_sub.add_parser("doc")
    doc.add_argument("path")
    chunks = catalog_sub.add_parser("chunks")
    chunks.add_argument("path")

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--repo-area", default=None)
    search.add_argument("--doc-type", default=None)
    search.add_argument("--include-historical", action="store_true")
    search.add_argument("--max-results", type=int, default=8)
    search.add_argument("--no-rerank", action="store_true")

    exact = sub.add_parser("exact")
    exact.add_argument("term")
    exact.add_argument("--repo-area", default=None)
    exact.add_argument("--include-historical", action="store_true")
    exact.add_argument("--max-results", type=int, default=20)

    open_doc = sub.add_parser("open")
    open_doc.add_argument("path")
    open_doc.add_argument("--heading", default=None)
    open_doc.add_argument("--line-start", type=int, default=None)
    open_doc.add_argument("--line-end", type=int, default=None)

    sub.add_parser("doctor")
    models = sub.add_parser("models")
    models_sub = models.add_subparsers(dest="models_command", required=True)
    models_sub.add_parser("doctor")
    eval_parser = sub.add_parser("eval")
    eval_parser.add_argument("--suite", default="sample", choices=["sample", "canonical-topics"])
    eval_parser.add_argument("--no-rerank", action="store_true")
    sub.add_parser("mcp")
    return parser


def validate(config) -> dict[str, object]:
    catalog = Catalog(config)
    stats = catalog.stats()
    warnings: list[str] = []
    with catalog.connect() as conn:
        missing = conn.execute("SELECT path,title,status,warnings_json FROM documents WHERE status='inferred' OR warnings_json NOT IN ('[]','null','') LIMIT 200").fetchall()
        for row in missing:
            warnings.append(f"{row['path']}: status={row['status']} warnings={row['warnings_json']}")
        broken = conn.execute("SELECT source_path,target_path,line_number FROM links WHERE link_type='markdown' AND target_path NOT LIKE '#%' LIMIT 200").fetchall()
        for row in broken[:50]:
            target = str(row["target_path"]).split("#", 1)[0]
            if target and target.startswith(("http:", "https:", "mailto:")):
                continue
            # Full link resolution is intentionally conservative in MVP.
            if " " in target:
                warnings.append(f"{row['source_path']}:{row['line_number']}: link may need manual check -> {row['target_path']}")
    return {"ok": True, "stats": stats, "warnings": warnings[:200]}


def doctor(config) -> dict[str, object]:
    catalog = Catalog(config)
    stats = catalog.stats()
    with catalog.connect() as conn:
        inferred = [dict(r) for r in conn.execute("SELECT path,title,status FROM documents WHERE status='inferred' LIMIT 100")]
        historical = [dict(r) for r in conn.execute("SELECT path,title,status FROM documents WHERE status='historical' LIMIT 50")]
        canonical_missing_alias = [dict(r) for r in conn.execute("SELECT path,title FROM documents WHERE status='canonical' AND aliases_json='[]' LIMIT 50")]
    return {
        "stats": stats,
        "docs_without_metadata_or_inferred": inferred,
        "historical_sample": historical,
        "canonical_without_aliases": canonical_missing_alias,
        "notes": ["Qdrant/model health is checked during index build/search; exact and SQLite search remain available without Qdrant."],
    }


def models_doctor(config) -> dict[str, object]:
    checks: list[dict[str, object]] = []

    def ok(message: str) -> None:
        checks.append({"status": "OK", "message": message})

    def fail(message: str) -> dict[str, object]:
        checks.append({"status": "FAIL", "message": message})
        return {"ok": False, "checks": checks}

    try:
        import torch  # type: ignore

        cuda_available = bool(torch.cuda.is_available())
        device = torch.cuda.get_device_name(0) if cuda_available else "none"
        ok(f"torch available; cuda={cuda_available}; device={device}")
    except Exception as exc:
        return fail(f"torch import failed: {exc}")
    try:
        import FlagEmbedding  # type: ignore  # noqa: F401

        ok("FlagEmbedding available")
    except Exception as exc:
        return fail(f"FlagEmbedding import failed: {exc}")
    try:
        from qdrant_client import QdrantClient  # type: ignore

        client = QdrantClient(url=config.data["index"]["qdrant_url"])
        client.get_collections()
        ok("Qdrant reachable")
    except Exception as exc:
        return fail(f"Qdrant unreachable at {config.data['index']['qdrant_url']}: {exc}")
    try:
        from .local_bge_backend import BgeM3LocalBackend

        backend = BgeM3LocalBackend.from_locator_config(config)
        ok(f"use_fp16 resolved: {backend.use_fp16}")
        backend.load_embedding_model()
        ok("embedding model exact: BAAI/bge-m3")
        encoded = backend.encode_passages(
            [
                "License activation validates a client request on the server.",
                "This document explains Blender material baking.",
            ],
            return_sparse=True,
        )
        dense = encoded["dense"]
        if len(dense) != 2 or any(len(vector) != 1024 for vector in dense):
            return fail(f"embedding dimension mismatch: {[len(vector) for vector in dense]}")
        ok("embedding dimension: 1024")
        sparse = encoded.get("sparse") or []
        if len(sparse) != 2 or not sparse[0] or not sparse[1]:
            return fail("sparse lexical_weights not returned")
        ok("sparse lexical_weights returned")
        backend.load_reranker()
        ok("reranker model exact: BAAI/bge-reranker-v2-m3")
        scores = backend.rerank_pairs(
            [
                ("server license activation", "License activation validates a client request on the server."),
                ("server license activation", "This document explains Blender material baking."),
            ],
            normalize=True,
        )
        if len(scores) != 2:
            return fail("reranker did not return two scores")
        if scores[0] <= scores[1]:
            return fail(f"reranker relevance ordering failed: {scores}")
        ok("reranker scores returned")
        if config.data["models"].get("allow_model_fallback"):
            return fail("fallback is enabled")
        ok("fallback disabled")
        return {"ok": True, "checks": checks}
    except Exception as exc:
        return fail(f"Required local BGE model check failed. No fallback model is allowed. {exc}")


def eval_golden(config, suite: str = "sample", rerank: bool = True) -> dict[str, object]:
    retriever = Retriever(config)
    if suite == "canonical-topics":
        suite_path = config.root / ".workspace-docs" / "eval-canonical-topics.json"
        data = json.loads(suite_path.read_text(encoding="utf-8"))
        cases = []
        for case in data.get("cases", []):
            result = retriever.search(
                case["query"],
                repo_area=case.get("repo_area"),
                include_historical=False,
                max_results=5,
                rerank=rerank,
            )
            paths = [item["path"] for item in result.get("results", [])]
            expected = case.get("expected_docs", [])
            rank = next((index + 1 for index, path in enumerate(paths) if path in expected), None)
            cases.append(
                {
                    "id": case["id"],
                    "query": case["query"],
                    "repo_area": case.get("repo_area"),
                    "pass": bool(rank and rank <= 3),
                    "expected_rank": rank,
                    "confidence": result.get("confidence"),
                    "top_paths": paths[:3],
                    "top_statuses": [item["status"] for item in result.get("results", [])[:3]],
                    "top_citation": result.get("results", [{}])[0].get("citation") if result.get("results") else None,
                }
            )
        return {"suite": suite, "rerank": rerank, "all_passed": all(case["pass"] for case in cases), "cases": cases}
    candidates = config.root / ".workspace-docs" / "eval-candidates.yml"
    return {
        "status": "mvp",
        "message": "Golden eval harness is ready; this first tranche ships candidates instead of asserting uncertain expected docs.",
        "eval_candidates": str(candidates),
        "sample": retriever.search("server architecture", max_results=3, rerank=False),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve() if args.root else find_workspace(Path.cwd())
    config = load_config(root)
    if args.command == "index":
        try:
            result = Catalog(config).rebuild() if args.index_command == "build" else Catalog(config).update()
        except (ModelConfigurationError, ModelLoadError) as exc:
            emit({"ok": False, "error": str(exc), "message": "Required local BGE-M3/reranker model check failed. No fallback model is allowed."})
            return 1
        emit(result)
        return 0 if not result["errors"] else 1
    if args.command == "catalog":
        catalog = Catalog(config)
        if args.catalog_command == "stats":
            emit(catalog.stats())
        elif args.catalog_command == "doc":
            emit(catalog.doc(args.path) or {"error": "not_found", "path": args.path})
        else:
            emit(catalog.chunks_for_doc(args.path))
        return 0
    if args.command == "validate":
        result = validate(config)
        emit(result)
        return 0 if result["ok"] else 1
    if args.command == "search":
        emit(Retriever(config).search(args.query, args.repo_area, args.doc_type, args.include_historical, args.max_results, not args.no_rerank))
        return 0
    if args.command == "exact":
        emit(Retriever(config).exact(args.term, args.repo_area, args.include_historical, args.max_results))
        return 0
    if args.command == "open":
        emit(Retriever(config).open_doc(args.path, args.heading, args.line_start, args.line_end))
        return 0
    if args.command == "doctor":
        emit(doctor(config))
        return 0
    if args.command == "models":
        result = models_doctor(config)
        for check in result["checks"]:
            print(f"[{check['status']}] {check['message']}")
        return 0 if result["ok"] else 1
    if args.command == "eval":
        emit(eval_golden(config, args.suite, not args.no_rerank))
        return 0
    if args.command == "mcp":
        from .mcp_server import run_stdio

        run_stdio(config)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

