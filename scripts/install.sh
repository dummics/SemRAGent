#!/usr/bin/env sh
set -eu

INSTALL_DIR="${INSTALL_DIR:-"$HOME/.workspace-docs-mcp"}"
REPO_URL="${REPO_URL:-"https://github.com/dummics/workspace-docs-mcp.git"}"
MODE="${1:-all}"

if ! command -v git >/dev/null 2>&1; then
  echo "[FAIL] Git is required." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "[FAIL] Python 3.11+ is required." >&2
  exit 1
fi

if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only
elif [ -e "$INSTALL_DIR" ]; then
  echo "[FAIL] INSTALL_DIR exists but is not a git checkout: $INSTALL_DIR" >&2
  exit 1
else
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

python3 -m venv "$INSTALL_DIR/.venv"
PY="$INSTALL_DIR/.venv/bin/python"
"$PY" -m pip install --upgrade pip setuptools wheel

if [ "$MODE" = "dev" ]; then
  "$PY" -m pip install -e "$INSTALL_DIR[dev,all]"
else
  "$PY" -m pip install -e "$INSTALL_DIR[all]"
fi

mkdir -p "$INSTALL_DIR/bin"
cat > "$INSTALL_DIR/bin/semragent" <<EOF
#!/usr/bin/env sh
exec "$PY" -m workspace_docs_mcp.cli "\$@"
EOF
cat > "$INSTALL_DIR/bin/workspace-docs" <<EOF
#!/usr/bin/env sh
exec "$PY" -m workspace_docs_mcp.cli "\$@"
EOF
cat > "$INSTALL_DIR/bin/workspace-docs-mcp" <<EOF
#!/usr/bin/env sh
exec "$PY" -c "from workspace_docs_mcp.cli import mcp_main; raise SystemExit(mcp_main())" "\$@"
EOF
chmod +x "$INSTALL_DIR/bin/semragent" "$INSTALL_DIR/bin/workspace-docs" "$INSTALL_DIR/bin/workspace-docs-mcp"

echo "[OK] Installed workspace-docs-mcp in $INSTALL_DIR"
echo "CLI: $INSTALL_DIR/bin/semragent"
echo "CLI: $INSTALL_DIR/bin/workspace-docs"
echo "MCP: $INSTALL_DIR/bin/workspace-docs-mcp"
