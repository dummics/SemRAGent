from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import LocatorConfig
from .model import Chunk, Document


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
STATUS_ALIASES = {
    "evidence": "support",
    "planned": "active",
    "legacy": "historical",
    "archive": "archived",
}


def rel_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return "#" + text.strip("-")


def git_commit(root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def modified_time(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def parse_frontmatter(lines: list[str]) -> tuple[dict[str, Any], int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    end = None
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = idx
            break
    if end is None:
        return {}, 0
    raw = "\n".join(lines[1:end])
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(raw) or {}
        return (data if isinstance(data, dict) else {}), end + 1
    except Exception:
        data: dict[str, Any] = {}
        current_key: str | None = None
        for line in raw.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line.startswith("  - ") and current_key:
                data.setdefault(current_key, []).append(line[4:].strip())
                continue
            if ":" in line and not line.startswith(" "):
                key, value = line.split(":", 1)
                current_key = key.strip()
                value = value.strip()
                if value == "[]":
                    data[current_key] = []
                elif value in {"null", "None", ""}:
                    data[current_key] = None if value else ""
                else:
                    data[current_key] = value.strip("\"'")
        return data, end + 1


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)] if str(value).strip() else []


def infer_repo_area(path: str) -> str:
    p = path.replace("\\", "/").lower()
    if p.startswith("server/") or "/server/" in p or p.startswith("docs/server") or "/backend/" in p:
        return "server"
    if p.startswith("client/") or "/client/" in p or p.startswith("docs/client") or "/frontend/" in p:
        return "client"
    if ".codex" in p or "agent" in p or p.startswith("catalog/"):
        return "agent-workflow"
    return "framework"


def infer_status(path: str, config: LocatorConfig, nav_paths: set[str], generated_status: dict[str, dict[str, Any]]) -> tuple[str, float, list[str]]:
    p = path.replace("\\", "/")
    pl = p.lower()
    warnings: list[str] = []
    generated = generated_status.get(p) or generated_status.get(p.removeprefix("docs/"))
    if generated:
        status = str(generated.get("status") or generated.get("authority") or "active")
        authority_label = str(generated.get("authority") or status)
        if authority_label == "canonical":
            status = "canonical"
        status = STATUS_ALIASES.get(status, status)
        return status, config.status_authority(status), warnings
    if p in nav_paths or p.removeprefix("docs/") in nav_paths:
        return "canonical", config.status_authority("canonical"), warnings
    if any(x in pl for x in ["/archive/", "/reviews/", "/historical/", "/docs_old", "/work/"]):
        return "historical", config.status_authority("historical"), warnings
    if "/generated/" in pl or pl.startswith("catalog/generated/"):
        return "generated", config.status_authority("generated"), warnings
    if "/operations/" in pl or "runbook" in pl:
        return "runbook", config.status_authority("runbook"), warnings
    warnings.append("missing_frontmatter_status_inferred")
    return "inferred", config.status_authority("inferred"), warnings


def infer_doc_type(path: str, title: str) -> str:
    p = path.lower()
    t = title.lower()
    if "runbook" in p or "operations" in p:
        return "runbook"
    if "architecture" in p or "architecture" in t:
        return "architecture"
    if "troubleshoot" in p or "debug" in p:
        return "troubleshooting"
    if "decision" in p or "rfc" in p:
        return "decision"
    if "api" in p or "contract" in p:
        return "api"
    if "generated" in p:
        return "generated"
    if "review" in p or "archive" in p or "work/" in p:
        return "historical"
    return "doc"


def title_from_lines(path: str, lines: list[str], frontmatter: dict[str, Any]) -> str:
    if frontmatter.get("title"):
        return str(frontmatter["title"])
    for line in lines:
        m = HEADING_RE.match(line)
        if m:
            return m.group(2).strip()
    return Path(path).stem.replace("-", " ").replace("_", " ").title()


def load_manifest_context(root: Path) -> tuple[set[str], dict[str, dict[str, Any]]]:
    nav_paths: set[str] = set()
    generated: dict[str, dict[str, Any]] = {}
    nav = root / "docs" / "navigation.json"
    if nav.exists():
        try:
            data = json.loads(nav.read_text(encoding="utf-8"))
            for doc in data.get("docs", []):
                if "path" in doc:
                    nav_paths.add("docs/" + str(doc["path"]).replace("\\", "/"))
                    nav_paths.add(str(doc["path"]).replace("\\", "/"))
        except Exception:
            pass
    idx = root / "catalog" / "generated" / "docs-index.jsonl"
    if idx.exists():
        for line in idx.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            path = str(item.get("path", "")).replace("\\", "/")
            if path:
                generated[path] = item
    return nav_paths, generated


def discover_markdown(config: LocatorConfig) -> list[Path]:
    results: list[Path] = []
    excludes = {str(x).lower() for x in config.data["paths"]["exclude"]}
    for root in config.docs_roots():
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            parts = {p.lower() for p in path.relative_to(config.root).parts}
            if parts.intersection(excludes):
                continue
            results.append(path)
    return sorted(set(results))


def parse_document(path: Path, config: LocatorConfig, nav_paths: set[str], generated_status: dict[str, dict[str, Any]], commit: str) -> tuple[Document, list[Chunk], list[dict[str, Any]]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    frontmatter, body_start = parse_frontmatter(lines)
    rp = rel_path(config.root, path)
    title = title_from_lines(rp, lines[body_start:], frontmatter)
    status = str(frontmatter.get("status") or "")
    warnings: list[str] = []
    if status:
        status = STATUS_ALIASES.get(status, status)
        authority = float(frontmatter.get("authority") or config.status_authority(status))
    else:
        status, authority, warnings = infer_status(rp, config, nav_paths, generated_status)
    doc_type = str(frontmatter.get("doc_type") or infer_doc_type(rp, title))
    repo_area = str(frontmatter.get("repo_area") or infer_repo_area(rp))
    aliases = normalize_list(frontmatter.get("aliases"))
    canonical_for = normalize_list(frontmatter.get("canonical_for"))
    document_id = str(frontmatter.get("id") or "lf." + re.sub(r"[^a-z0-9]+", ".", rp.lower()).strip("."))
    doc = Document(
        document_id=document_id,
        path=rp,
        title=title,
        status=status,
        doc_type=doc_type,
        repo_area=repo_area,
        authority=authority,
        aliases=aliases,
        canonical_for=canonical_for,
        supersedes=normalize_list(frontmatter.get("supersedes")),
        replaced_by=frontmatter.get("replaced_by"),
        last_reviewed=frontmatter.get("last_reviewed"),
        review_status=frontmatter.get("review_status"),
        content_hash=sha256_text(text),
        git_commit=commit,
        last_modified=modified_time(path),
        frontmatter=frontmatter,
        warnings=warnings,
    )
    chunks = chunk_document(doc, lines, body_start, config)
    links = extract_links(rp, lines)
    return doc, chunks, links


def chunk_document(doc: Document, lines: list[str], body_start: int, config: LocatorConfig) -> list[Chunk]:
    headings: list[tuple[int, int, str, list[str]]] = []
    stack: list[tuple[int, str]] = []
    for index, line in enumerate(lines, start=1):
        if index <= body_start:
            continue
        m = HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        title = m.group(2).strip()
        stack = [h for h in stack if h[0] < level]
        stack.append((level, title))
        headings.append((index, level, title, [h[1] for h in stack]))

    if not headings:
        headings = [(max(1, body_start + 1), 1, doc.title, [doc.title])]

    chunks: list[Chunk] = []
    for idx, (start, _level, heading, heading_path) in enumerate(headings):
        end = (headings[idx + 1][0] - 1) if idx + 1 < len(headings) else len(lines)
        section_lines = lines[start - 1 : end]
        section_text = "\n".join(section_lines).strip()
        if not section_text:
            continue
        chunks.extend(split_section(doc, heading_path, heading, start, end, section_text, config))
    return chunks


def split_section(doc: Document, heading_path: list[str], heading: str, line_start: int, line_end: int, text: str, config: LocatorConfig) -> list[Chunk]:
    max_tokens = int(config.data["index"]["max_chunk_tokens"])
    words = text.split()
    blocks: list[tuple[int, int, str]]
    if len(words) <= max_tokens:
        blocks = [(line_start, line_end, text)]
    else:
        lines = text.splitlines()
        blocks = []
        chunk_lines: list[str] = []
        chunk_start = line_start
        token_count = 0
        for offset, line in enumerate(lines):
            token_count += max(1, len(line.split()))
            chunk_lines.append(line)
            if token_count >= max_tokens:
                current_end = line_start + offset
                blocks.append((chunk_start, current_end, "\n".join(chunk_lines).strip()))
                chunk_lines = []
                chunk_start = current_end + 1
                token_count = 0
        if chunk_lines:
            blocks.append((chunk_start, line_end, "\n".join(chunk_lines).strip()))
    chunks: list[Chunk] = []
    for start, end, chunk_text in blocks:
        text_for_embedding = (
            f"Document: {doc.title}\nPath: {doc.path}\nStatus: {doc.status}\nDoc type: {doc.doc_type}\n"
            f"Repo area: {doc.repo_area}\nHeading: {' > '.join(heading_path)}\nAliases: {', '.join(doc.aliases)}\nContent:\n{chunk_text}"
        )
        chunks.append(
            Chunk(
                chunk_id=f"{doc.path}{slugify(heading)}:{start}-{end}",
                document_id=doc.document_id,
                path=doc.path,
                title=doc.title,
                status=doc.status,
                doc_type=doc.doc_type,
                repo_area=doc.repo_area,
                authority=doc.authority,
                heading_path=heading_path,
                anchor=slugify(heading),
                line_start=start,
                line_end=end,
                text=chunk_text,
                text_for_embedding=text_for_embedding,
                token_estimate=max(1, len(chunk_text.split())),
                content_hash=sha256_text(chunk_text),
                git_commit=doc.git_commit,
                last_modified=doc.last_modified,
                chunker_version=config.chunker_version,
                embedding_model=config.embedding_model,
                aliases=doc.aliases,
                topics=doc.canonical_for,
            )
        )
    return chunks


def extract_links(path: str, lines: list[str]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        for match in LINK_RE.finditer(line):
            target = match.group(2).strip()
            link_type = "external" if re.match(r"^[a-z]+://", target) else "markdown"
            links.append({"source_path": path, "target_path": target, "link_text": match.group(1), "link_type": link_type, "line_number": index})
    return links

