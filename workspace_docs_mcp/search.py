from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .catalog import Catalog
from .config import LocatorConfig
from .model import SearchResult
from .vector import VectorIndex
from .local_bge_backend import BgeM3LocalBackend


TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]+")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def score(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(1.0, float(value))), 3)


def snippet(text: str, query: str, max_len: int = 180) -> str:
    lower = text.lower()
    for term in tokenize(query):
        pos = lower.find(term)
        if pos >= 0:
            start = max(0, pos - 120)
            end = min(len(text), pos + max_len)
            return text[start:end].replace("\n", " ").strip()
    return text[:max_len].replace("\n", " ").strip()


class Retriever:
    def __init__(self, config: LocatorConfig):
        self.config = config
        self.catalog = Catalog(config)

    def allowed_status_clause(self, include_historical: bool) -> tuple[str, list[str]]:
        excluded = set(self.config.data["policy"]["exclude_by_default"])
        if not include_historical and self.config.data["policy"].get("historical_requires_flag", True):
            excluded.add("historical")
        placeholders = ",".join("?" for _ in excluded)
        return (f"status NOT IN ({placeholders})", list(excluded)) if excluded else ("1=1", [])

    def search(self, query: str, repo_area: str | None = None, doc_type: str | None = None, include_historical: bool = False, max_results: int = 8, rerank: bool = True, dedupe_documents: bool = True, verbosity: str = "compact") -> dict[str, Any]:
        self.catalog.init()
        candidates: dict[str, SearchResult] = {}
        warnings: list[str] = []
        for result in self.lexical_search(query, repo_area, doc_type, include_historical, int(self.config.data["retrieval"]["candidate_limit_lexical"])):
            candidates[result.path + str(result.line_start)] = result
        for result in self.alias_and_exact_candidates(query, repo_area, include_historical):
            key = result.path + str(result.line_start)
            if key in candidates:
                candidates[key].exact_score = max(candidates[key].exact_score, result.exact_score)
                candidates[key].why.append("exact/alias match")
            else:
                candidates[key] = result
        try:
            dense_results = self.dense_candidates(query, repo_area, doc_type, include_historical)
        except Exception as exc:
            message = str(exc)
            if "BAAI/bge" in message or "Required embedding model" in message or "No fallback model is allowed" in message:
                raise
            warnings.append(f"vector_index_unavailable: {message}")
            dense_results = []
        for result in dense_results:
            key = result.path + str(result.line_start)
            if key in candidates:
                candidates[key].dense_score = max(candidates[key].dense_score, result.dense_score)
                candidates[key].sparse_score = max(candidates[key].sparse_score, result.sparse_score)
                candidates[key].why.append("semantic match")
            else:
                candidates[key] = result
        results = list(candidates.values())
        self.apply_scores(results, query)
        if rerank:
            rerank_warning = self.try_rerank(query, results)
            if rerank_warning:
                warnings.append(rerank_warning)
        results.sort(key=lambda r: r.score, reverse=True)
        if dedupe_documents:
            best_by_path: dict[str, SearchResult] = {}
            for result in results:
                if result.path not in best_by_path:
                    best_by_path[result.path] = result
            results = list(best_by_path.values())
        results = results[:max_results]
        confidence, reasons, suggested = self.confidence(results, query)
        return {
            "query": query,
            "intent": "locate_doc",
            "confidence": confidence,
            "confidence_reasons": reasons,
            "warnings": warnings,
            "results": [self.result_json(r, verbosity=verbosity) for r in results],
            "suggested_next_queries": suggested,
        }

    def lexical_search(self, query: str, repo_area: str | None, doc_type: str | None, include_historical: bool, limit: int) -> list[SearchResult]:
        status_clause, params = self.allowed_status_clause(include_historical)
        filters = [status_clause]
        if repo_area and repo_area != "any":
            filters.append("repo_area=?")
            params.append(repo_area)
        if doc_type and doc_type != "any":
            filters.append("doc_type=?")
            params.append(doc_type)
        where = " AND ".join(filters)
        fts_query = " OR ".join(tokenize(query)) or query
        sql = f"""
            SELECT c.*, bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
            WHERE chunks_fts MATCH ? AND {where}
            ORDER BY rank LIMIT ?
        """
        out: list[SearchResult] = []
        with self.catalog.connect() as conn:
            try:
                rows = conn.execute(sql, [fts_query, *params, limit]).fetchall()
            except Exception:
                rows = conn.execute(f"SELECT * FROM chunks WHERE {where} LIMIT ?", [*params, limit]).fetchall()
            for row in rows:
                lexical = 1.0 / (1.0 + abs(float(row["rank"]))) if "rank" in row.keys() else 0.35
                out.append(self.row_to_result(row, query, lexical_score=lexical, why=["lexical match"]))
        return out

    def dense_candidates(self, query: str, repo_area: str | None, doc_type: str | None, include_historical: bool) -> list[SearchResult]:
        hits = VectorIndex(self.config).search_chunks(query, int(self.config.data["retrieval"].get("rerank_candidates", 50)))
        if not hits:
            return []
        status_excluded = set(self.config.data["policy"]["exclude_by_default"])
        if not include_historical:
            status_excluded.add("historical")
        out: list[SearchResult] = []
        with self.catalog.connect() as conn:
            for hit in hits:
                payload = hit["payload"]
                if payload.get("status") in status_excluded:
                    continue
                if repo_area and repo_area != "any" and payload.get("repo_area") != repo_area:
                    continue
                if doc_type and doc_type != "any" and payload.get("doc_type") != doc_type:
                    continue
                row = conn.execute("SELECT * FROM chunks WHERE chunk_id=?", (payload.get("chunk_id"),)).fetchone()
                if not row:
                    continue
                out.append(self.row_to_result(row, query, why=["semantic match"], lexical_score=0.0, exact_score=0.0))
                out[-1].dense_score = float(hit.get("dense_score", hit.get("score", 0.0)))
                out[-1].sparse_score = float(hit.get("sparse_score", 0.0))
        return out

    def alias_and_exact_candidates(self, query: str, repo_area: str | None, include_historical: bool) -> list[SearchResult]:
        status_clause, params = self.allowed_status_clause(include_historical)
        out: list[SearchResult] = []
        q = query.strip().lower()
        query_terms = set(tokenize(query))
        with self.catalog.connect() as conn:
            alias_rows = conn.execute(
                f"""
                SELECT c.*, a.weight
                FROM aliases a JOIN chunks c ON c.document_id=a.document_id
                WHERE lower(a.alias)=? AND {status_clause}
                ORDER BY a.weight DESC, c.authority DESC LIMIT 20
                """,
                [q, *params],
            ).fetchall()
            for row in alias_rows:
                if repo_area and repo_area != "any" and row["repo_area"] != repo_area:
                    continue
                out.append(self.row_to_result(row, query, exact_score=0.95, why=["alias match"]))
            route_rows = conn.execute(
                "SELECT target_path, repo_area, topic FROM routes WHERE lower(topic)=? AND (? IS NULL OR ?='any' OR repo_area=? OR repo_area='any') ORDER BY priority LIMIT 20",
                [q, repo_area, repo_area, repo_area],
            ).fetchall()
            for route in route_rows:
                chunk_rows = conn.execute(
                    f"SELECT * FROM chunks WHERE path=? AND {status_clause} ORDER BY authority DESC, line_start ASC LIMIT 10",
                    [route["target_path"], *params],
                ).fetchall()
                for row in chunk_rows:
                    out.append(self.row_to_result(row, query, exact_score=0.95, why=["route alias match"]))
            title_rows = conn.execute(
                f"""
                SELECT *
                FROM chunks
                WHERE lower(title)=? AND {status_clause}
                ORDER BY authority DESC, line_start ASC LIMIT 30
                """,
                [q, *params],
            ).fetchall()
            for row in title_rows:
                if repo_area and repo_area != "any" and row["repo_area"] != repo_area:
                    continue
                out.append(self.row_to_result(row, query, exact_score=0.95, why=["title match"]))
            title_like_filters = " OR ".join("lower(title) LIKE ?" for _ in query_terms)
            title_like_rows = conn.execute(
                f"""
                SELECT *
                FROM chunks
                WHERE ({title_like_filters}) AND {status_clause}
                ORDER BY authority DESC, line_start ASC LIMIT 50
                """,
                [*[f"%{term}%" for term in query_terms], *params],
            ).fetchall()
            for row in title_like_rows:
                if repo_area and repo_area != "any" and row["repo_area"] != repo_area:
                    continue
                title_terms = set(tokenize(str(row["title"]) + " " + str(row["path"])))
                overlap = len(query_terms.intersection(title_terms)) / max(1, len(query_terms))
                if overlap >= 0.35:
                    out.append(self.row_to_result(row, query, exact_score=min(0.85, overlap), why=["partial title/path match"]))
            term_filters = " OR ".join("lower(a.alias) LIKE ?" for _ in query_terms)
            alias_like_rows = conn.execute(
                f"""
                SELECT c.*, a.alias, a.weight
                FROM aliases a JOIN chunks c ON c.document_id=a.document_id
                WHERE ({term_filters}) AND {status_clause}
                ORDER BY a.weight DESC, c.authority DESC LIMIT 30
                """,
                [*[f"%{term}%" for term in query_terms], *params],
            ).fetchall()
            for row in alias_like_rows:
                if repo_area and repo_area != "any" and row["repo_area"] != repo_area:
                    continue
                alias_terms = set(tokenize(str(row["alias"]) + " " + str(row["title"]) + " " + str(row["path"])))
                overlap = len(query_terms.intersection(alias_terms)) / max(1, len(query_terms))
                out.append(self.row_to_result(row, query, exact_score=max(0.55, min(0.85, overlap)), why=["partial alias match"]))
            path_rows = conn.execute(
                f"SELECT * FROM chunks WHERE lower(path) LIKE ? AND {status_clause} ORDER BY authority DESC LIMIT 20",
                [f"%{q}%", *params],
            ).fetchall()
            for row in path_rows:
                if repo_area and repo_area != "any" and row["repo_area"] != repo_area:
                    continue
                out.append(self.row_to_result(row, query, exact_score=0.85, why=["path match"]))
        return out

    def row_to_result(self, row: Any, query: str, lexical_score: float = 0.0, exact_score: float = 0.0, why: list[str] | None = None) -> SearchResult:
        return SearchResult(
            path=row["path"],
            title=row["title"],
            status=row["status"],
            doc_type=row["doc_type"],
            repo_area=row["repo_area"],
            authority=float(row["authority"]),
            line_start=int(row["line_start"]),
            line_end=int(row["line_end"]),
            heading_path=json.loads(row["heading_path_json"] or "[]"),
            anchor=row["anchor"],
            snippet=snippet(row["text"], query),
            score=0.0,
            lexical_score=lexical_score,
            exact_score=exact_score,
            authority_score=float(row["authority"]),
            freshness_score=0.6,
            why=why or [],
        )

    def apply_scores(self, results: list[SearchResult], query: str) -> None:
        terms = set(tokenize(query))
        for r in results:
            route = 0.0
            if r.repo_area in terms or any(t in r.path.lower() for t in terms):
                route = 0.4
            r.route_match_score = route
            if r.status == "canonical":
                r.policy_adjustments.append("canonical_boost")
                policy = 0.08
            elif r.status == "runbook":
                policy = 0.05
            elif r.status == "generated":
                r.policy_adjustments.append("generated_lower_priority")
                policy = -0.04
            elif r.status == "historical":
                r.policy_adjustments.append("historical_suppressed")
                policy = -0.20
            else:
                policy = 0.0
            r.score = max(
                0.0,
                min(
                    1.0,
                    0.30 * r.lexical_score
                    + 0.07 * r.dense_score
                    + 0.05 * r.sparse_score
                    + 0.25 * r.exact_score
                    + 0.13 * r.authority_score
                    + 0.10 * r.route_match_score
                    + 0.05 * r.freshness_score
                    + policy,
                ),
            )

    def try_rerank(self, query: str, results: list[SearchResult]) -> str | None:
        limit = min(int(self.config.data["retrieval"]["rerank_candidates"]), 100, len(results))
        if not limit:
            return None
        backend = BgeM3LocalBackend.from_locator_config(self.config)
        pairs = [(query, f"{r.title}\n{' > '.join(r.heading_path)}\n{r.snippet}") for r in results[:limit]]
        scores = backend.rerank_pairs(pairs, normalize=True)
        for r, score in zip(results[:limit], scores):
            r.reranker_score = float(score)
            r.score = min(1.0, 0.65 * float(score) + 0.35 * r.score)
            if "reranker match" not in r.why:
                r.why.append("reranker match")
        return None

    def confidence(self, results: list[SearchResult], query: str) -> tuple[str, list[str], list[str]]:
        if not results:
            return "low", ["no semantic candidates found"], ["retry find_docs after index_status is fresh"]
        top = results[0]
        second = results[1].score if len(results) > 1 else 0.0
        margin = top.score - second
        reasons: list[str] = []
        if top.status in {"canonical", "runbook", "active"}:
            reasons.append(f"top result is {top.status}")
        if top.lexical_score > 0.2 and (top.exact_score > 0.0 or top.reranker_score is not None):
            reasons.append("lexical signal agrees with another signal")
        if top.exact_score >= 0.85:
            reasons.append("strong exact/title/alias match")
        if top.line_start > 0 and top.line_end >= top.line_start:
            reasons.append("valid line citation")
        if margin > 0.12:
            reasons.append("clear top-result margin")
        if top.reranker_score is not None and top.reranker_score >= 0.55:
            reasons.append("reranker score is strong")
        if top.dense_score > 0.0:
            reasons.append("dense vector signal present")
        if top.sparse_score > 0.0:
            reasons.append("sparse lexical vector signal present")
        if top.status in {"canonical", "runbook", "active"} and top.reranker_score is not None and top.reranker_score >= 0.55 and "valid line citation" in reasons:
            return "high", reasons, []
        if top.status in {"canonical", "runbook", "active"} and top.exact_score >= 0.85 and "valid line citation" in reasons:
            return "high", reasons, []
        if top.score >= float(self.config.data["confidence"]["high_min_score"]) and top.status in {"canonical", "runbook", "active"} and "valid line citation" in reasons:
            return "high", reasons, []
        if top.score >= float(self.config.data["confidence"]["medium_min_score"]):
            return "medium", reasons or ["plausible hybrid match"], []
        return "low", reasons or ["weak or ambiguous retrieval signals"], ["add alias/frontmatter or narrow the query"]

    def result_json(self, r: SearchResult, verbosity: str = "compact") -> dict[str, Any]:
        signals = {
            "reranker": score(r.reranker_score),
            "dense": score(r.dense_score),
            "sparse": score(r.sparse_score),
            "lexical": score(r.lexical_score),
            "exact": score(r.exact_score),
        }
        compact = {
            "path": r.path,
            "title": r.title,
            "status": r.status,
            "doc_type": r.doc_type,
            "repo_area": r.repo_area,
            "score": score(r.score),
            "signals": signals,
            "why": sorted(set(r.why + (["canonical document"] if r.status == "canonical" else []))),
            "section": {"heading": " > ".join(r.heading_path), "line_start": r.line_start, "line_end": r.line_end},
            "citation": r.citation,
        }
        if r.snippet:
            compact["snippet"] = r.snippet[:220]
        if verbosity == "full":
            compact["authority"] = score(r.authority)
            compact["final_score"] = score(r.score)
            compact["signals"] = {
                **signals,
                "qdrant": score(max(r.dense_score, r.sparse_score)),
                "authority": score(r.authority_score),
                "route": score(r.route_match_score),
                "freshness": score(r.freshness_score),
            }
            compact["policy_adjustments"] = r.policy_adjustments
            compact["best_sections"] = [{"heading": " > ".join(r.heading_path), "anchor": r.anchor, "line_start": r.line_start, "line_end": r.line_end}]
        return compact

    def exact(self, term: str, repo_area: str | None = None, include_historical: bool = False, max_results: int = 20) -> dict[str, Any]:
        self.catalog.init()
        status_clause, params = self.allowed_status_clause(include_historical)
        results: list[dict[str, Any]] = []
        q = f"%{term}%"
        with self.catalog.connect() as conn:
            rows = conn.execute(
                f"SELECT path,line_start AS line_number,text AS snippet,'markdown' source_kind,title,status FROM chunks WHERE (text LIKE ? OR title LIKE ? OR path LIKE ?) AND {status_clause} LIMIT ?",
                [q, q, q, *params, max_results],
            ).fetchall()
            for row in rows:
                if repo_area and repo_area != "any":
                    doc = conn.execute("SELECT repo_area FROM documents WHERE path=?", (row["path"],)).fetchone()
                    if doc and doc["repo_area"] != repo_area:
                        continue
                results.append({"path": row["path"], "line_number": row["line_number"], "snippet": snippet(row["snippet"], term), "source_kind": row["source_kind"], "related_canonical_docs": []})
            remaining = max_results - len(results)
            if remaining > 0:
                sym_rows = conn.execute("SELECT * FROM symbols WHERE symbol LIKE ? LIMIT ?", (q, remaining)).fetchall()
                for row in sym_rows:
                    if repo_area and repo_area != "any" and row["repo_area"] != repo_area:
                        continue
                    results.append({"path": row["path"], "line_number": row["line_number"], "snippet": row["symbol"], "source_kind": row["source_kind"], "related_canonical_docs": []})
        conf = "high" if results and any(term.lower() in r["snippet"].lower() for r in results[:3]) else "medium" if results else "low"
        return {"term": term, "confidence": conf, "results": results[:max_results]}

    def open_doc(self, path: str, heading: str | None = None, line_start: int | None = None, line_end: int | None = None) -> dict[str, Any]:
        normalized = path.replace("\\", "/").lstrip("/")
        target = (self.config.root / normalized).resolve()
        if not str(target).lower().startswith(str(self.config.root).lower()):
            raise ValueError("path outside workspace is blocked")
        if not target.exists():
            raise FileNotFoundError(normalized)
        lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
        start = int(line_start or 1)
        end = int(line_end or len(lines))
        if heading:
            for idx, line in enumerate(lines, start=1):
                if heading.lower() in line.lower() and line.lstrip().startswith("#"):
                    start = idx
                    end = next((j - 1 for j in range(idx + 1, len(lines) + 1) if lines[j - 1].lstrip().startswith("#")), len(lines))
                    break
        start = max(1, start)
        end = min(len(lines), max(start, end))
        doc = self.catalog.doc(normalized) or {}
        return {
            "path": normalized,
            "title": doc.get("title") or Path(normalized).stem,
            "status": doc.get("status") or "unknown",
            "doc_type": doc.get("doc_type") or "unknown",
            "repo_area": doc.get("repo_area") or "unknown",
            "content": "\n".join(lines[start - 1 : end]),
            "line_start": start,
            "line_end": end,
            "citations": [{"path": normalized, "line_start": start, "line_end": end}],
        }

    def list_canonical(self, repo_area: str | None = None, topic: str | None = None) -> dict[str, Any]:
        self.catalog.init()
        params: list[Any] = ["canonical", "runbook"]
        filters = ["status IN (?,?)"]
        if repo_area and repo_area != "any":
            filters.append("repo_area=?")
            params.append(repo_area)
        if topic:
            filters.append("(lower(title) LIKE ? OR lower(path) LIKE ? OR lower(canonical_for_json) LIKE ?)")
            params.extend([f"%{topic.lower()}%"] * 3)
        with self.catalog.connect() as conn:
            rows = conn.execute(f"SELECT * FROM documents WHERE {' AND '.join(filters)} ORDER BY authority DESC,title LIMIT 100", params).fetchall()
        return {"results": [{"path": r["path"], "title": r["title"], "repo_area": r["repo_area"], "doc_type": r["doc_type"], "canonical_for": json.loads(r["canonical_for_json"] or "[]"), "aliases": json.loads(r["aliases_json"] or "[]")} for r in rows]}

    def neighbors(self, path: str, include_historical: bool = False) -> dict[str, Any]:
        normalized = path.replace("\\", "/")
        with self.catalog.connect() as conn:
            out = [dict(r) for r in conn.execute("SELECT target_path,link_text,link_type,line_number FROM links WHERE source_path=?", (normalized,))]
            inc = [dict(r) for r in conn.execute("SELECT source_path,link_text,link_type,line_number FROM links WHERE target_path LIKE ?", (f"%{normalized}%",))]
            doc = conn.execute("SELECT supersedes_json,replaced_by,repo_area FROM documents WHERE path=?", (normalized,)).fetchone()
            area = doc["repo_area"] if doc else None
            related = []
            if area:
                rows = conn.execute("SELECT path FROM documents WHERE repo_area=? AND path<>? AND status IN ('canonical','runbook') LIMIT 10", (area, normalized)).fetchall()
                related = [{"path": r["path"], "relation": "same_topic"} for r in rows]
        return {"path": normalized, "links_out": out, "links_in": inc, "supersedes": json.loads(doc["supersedes_json"] or "[]") if doc else [], "replaced_by": doc["replaced_by"] if doc else None, "related_docs": related}

    def explain(self, query: str, path: str) -> dict[str, Any]:
        result = self.search(query, max_results=20, verbosity="full")
        match = next((r for r in result["results"] if r["path"] == path.replace("\\", "/")), None)
        return {
            "query": query,
            "path": path,
            "explanation": {
                "matched_by": match["why"] if match else [],
                "scores": match["signals"] if match else {},
                "policy": match.get("policy_adjustments", []) if match else [],
                "is_safe_as_canonical": bool(match and match["status"] in {"canonical", "runbook"}),
                "warnings": [] if match else ["path_not_in_top_results"],
            },
        }

