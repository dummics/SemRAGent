from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

from .catalog import Catalog
from .config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="workspace-docs-index-worker")
    parser.add_argument("--root", required=True)
    parser.add_argument("--lock", required=True)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    lock = Path(args.lock).resolve()
    result_path = root / ".rag" / "index-worker-last-result.json"
    started = datetime.now(timezone.utc).isoformat()
    try:
        config = load_config(root)
        result = Catalog(config).update()
        payload = {
            "ok": not bool(result.get("errors")),
            "started_at": started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "docs": result.get("docs"),
            "chunks": result.get("chunks"),
            "errors": result.get("errors", [])[:20],
            "warnings_count": len(result.get("warnings", [])),
        }
        result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return 0 if payload["ok"] else 1
    except Exception as exc:
        payload = {
            "ok": False,
            "started_at": started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return 1
    finally:
        try:
            lock.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

