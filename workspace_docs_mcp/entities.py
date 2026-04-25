from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import LocatorConfig
from .markdown import rel_path


TERM_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass
class Entity:
    term: str
    aliases: list[str] = field(default_factory=list)
    entity_type: str = "term"
    definition: str = ""
    source_path: str = ""
    line_start: int = 1
    line_end: int = 1
    canonical_docs: list[str] = field(default_factory=list)
    authority: float = 0.7


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def parse_entities(config: LocatorConfig) -> list[Entity]:
    entities: list[Entity] = []
    for path in config.glob_sources("entity_sources"):
        if path.suffix.lower() == ".json":
            entities.extend(parse_json_entities(config, path))
        elif path.suffix.lower() in {".yml", ".yaml"}:
            entities.extend(parse_yaml_entities(config, path))
        elif path.suffix.lower() == ".md":
            entities.extend(parse_markdown_entities(config, path))
    return entities


def parse_json_entities(config: LocatorConfig, path: Path) -> list[Entity]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    items: list[Any]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("entities") or data.get("definitions") or data.get("terms") or []
        if isinstance(items, dict):
            items = [{"term": key, **(value if isinstance(value, dict) else {"definition": value})} for key, value in items.items()]
    else:
        items = []
    return [entity_from_mapping(config, path, item) for item in items if isinstance(item, dict)]


def parse_yaml_entities(config: LocatorConfig, path: Path) -> list[Entity]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("entities") or data.get("definitions") or data.get("terms") or []
        if isinstance(items, dict):
            items = [{"term": key, **(value if isinstance(value, dict) else {"definition": value})} for key, value in items.items()]
    else:
        items = []
    return [entity_from_mapping(config, path, item) for item in items if isinstance(item, dict)]


def entity_from_mapping(config: LocatorConfig, path: Path, item: dict[str, Any]) -> Entity:
    term = str(item.get("term") or item.get("name") or item.get("id") or "").strip()
    definition = str(item.get("definition") or item.get("description") or item.get("summary") or "").strip()
    return Entity(
        term=term,
        aliases=normalize_list(item.get("aliases")),
        entity_type=str(item.get("entity_type") or item.get("type") or "term"),
        definition=definition,
        source_path=rel_path(config.root, path),
        line_start=int(item.get("line_start") or 1),
        line_end=int(item.get("line_end") or 1),
        canonical_docs=normalize_list(item.get("canonical_docs") or item.get("canonical_for") or item.get("docs")),
        authority=float(item.get("authority") or 0.85),
    )


def parse_markdown_entities(config: LocatorConfig, path: Path) -> list[Entity]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    headings: list[tuple[int, str]] = []
    for index, line in enumerate(lines, start=1):
        match = TERM_HEADING_RE.match(line)
        if match:
            headings.append((index, match.group(2).strip()))
    if not headings:
        return []
    out: list[Entity] = []
    for offset, (start, title) in enumerate(headings):
        end = headings[offset + 1][0] - 1 if offset + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        if not body:
            continue
        aliases = []
        alias_match = re.search(r"(?im)^aliases?\s*:\s*(.+)$", body)
        if alias_match:
            aliases = [part.strip() for part in re.split(r"[,;]", alias_match.group(1)) if part.strip()]
        out.append(
            Entity(
                term=title,
                aliases=aliases,
                entity_type="definition",
                definition=body,
                source_path=rel_path(config.root, path),
                line_start=start,
                line_end=end,
                authority=0.8,
            )
        )
    return out

