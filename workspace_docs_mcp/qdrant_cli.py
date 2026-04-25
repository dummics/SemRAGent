from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .config import LocatorConfig


def qdrant_config(config: LocatorConfig) -> dict[str, Any]:
    qdrant = dict(config.data.get("qdrant", {}))
    index = config.data.get("index", {})
    return {
        "url": qdrant.get("url") or index.get("qdrant_url", "http://localhost:6333"),
        "docker_container": qdrant.get("docker_container", "semragent-qdrant"),
        "docker_image": qdrant.get("docker_image", "qdrant/qdrant"),
        "storage_path": str((config.root / qdrant.get("storage_path", ".rag/qdrant")).resolve()),
    }


def qdrant_status(config: LocatorConfig) -> dict[str, Any]:
    cfg = qdrant_config(config)
    collections = []
    try:
        from qdrant_client import QdrantClient  # type: ignore

        client = QdrantClient(url=cfg["url"])
        names = [item.name for item in client.get_collections().collections]
        for name in names:
            count = int(client.count(name, exact=True).count)
            collections.append({"name": name, "points": count})
        return {"ok": True, "url": cfg["url"], "collections": collections}
    except Exception as exc:
        return {
            "ok": False,
            "url": cfg["url"],
            "error": str(exc),
            "owner_action": {
                "summary": "Start Qdrant or update qdrant.url in config.",
                "commands": ["semragent qdrant start"],
                "safe_for_agent": False,
            },
        }


def qdrant_start(config: LocatorConfig) -> dict[str, Any]:
    cfg = qdrant_config(config)
    if not docker_available():
        return {"ok": False, "error": "Docker CLI is not available.", "owner_action": "Install Docker Desktop or start Qdrant manually."}
    storage = Path(cfg["storage_path"])
    storage.mkdir(parents=True, exist_ok=True)
    existing = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name=^/{cfg['docker_container']}$", "--format", "{{.Names}}"],
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()
    if existing == cfg["docker_container"]:
        proc = subprocess.run(["docker", "start", cfg["docker_container"]], text=True, capture_output=True, check=False)
        return {"ok": proc.returncode == 0, "action": "start", "container": cfg["docker_container"], "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}
    proc = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            cfg["docker_container"],
            "-p",
            "6333:6333",
            "-v",
            f"{storage}:/qdrant/storage",
            cfg["docker_image"],
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    return {"ok": proc.returncode == 0, "action": "create", "container": cfg["docker_container"], "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def qdrant_stop(config: LocatorConfig) -> dict[str, Any]:
    cfg = qdrant_config(config)
    if not docker_available():
        return {"ok": False, "error": "Docker CLI is not available."}
    proc = subprocess.run(["docker", "stop", cfg["docker_container"]], text=True, capture_output=True, check=False)
    return {"ok": proc.returncode == 0, "container": cfg["docker_container"], "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def docker_available() -> bool:
    try:
        return subprocess.run(["docker", "--version"], capture_output=True, check=False).returncode == 0
    except Exception:
        return False
