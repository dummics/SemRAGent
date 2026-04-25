#!/usr/bin/env sh
set -eu

SOURCE="${SOURCE:-"$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"}"
WORKDIR="${WORKDIR:-"$(mktemp -d)"}"
KEEP="${KEEP:-0}"

cleanup() {
  if [ "$KEEP" != "1" ] && [ -d "$WORKDIR" ]; then
    rm -rf "$WORKDIR"
  fi
}
trap cleanup EXIT

echo "==> Creating clean smoke workspace"
git clone "$SOURCE" "$WORKDIR/repo" >/dev/null

echo "==> Creating virtual environment"
python3 -m venv "$WORKDIR/.venv"
PY="$WORKDIR/.venv/bin/python"
"$PY" -m pip install --upgrade pip setuptools wheel >/dev/null

echo "==> Installing package without model extras"
"$PY" -m pip install -e "$WORKDIR/repo[dev]" >/dev/null

echo "==> Running CLI smoke"
"$PY" -m workspace_docs_mcp.cli --help >/dev/null
"$PY" -m workspace_docs_mcp.cli --root "$WORKDIR/repo" init --preset generic --force >/dev/null
"$PY" -m workspace_docs_mcp.cli --root "$WORKDIR/repo" qdrant status >/dev/null || echo "[WARN] Qdrant unavailable during smoke; this is allowed for install-only smoke."
"$PY" -m workspace_docs_mcp.cli --root "$WORKDIR/repo" lint-authority --json >/dev/null
"$PY" -m workspace_docs_mcp.cli --root "$WORKDIR/repo" eval bootstrap >/dev/null

echo "==> Running tests"
cd "$WORKDIR/repo"
"$PY" -m unittest discover -s tests -v

echo "[OK] Smoke install passed: $WORKDIR"
