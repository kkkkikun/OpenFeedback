#!/usr/bin/env bash
# Sync the repo to the private build host and run the server test suite.
set -euo pipefail

REPO_DIR="${OF_REPO_DIR:-$HOME/work/OpenFeedback}"
PRIVATE_HOST="${OF_PRIVATE_HOST:-172.16.38.110}"
PRIVATE_PORT="${OF_PRIVATE_PORT:-56127}"
PRIVATE_USER="${OF_PRIVATE_USER:-kikun}"

echo "=== rsync repo -> $PRIVATE_HOST:$REPO_DIR ==="
rsync -az --delete \
  -e "ssh -p $PRIVATE_PORT" \
  --exclude '.git' \
  --exclude '.ssh_helper.py' \
  --exclude '**/__pycache__' \
  --exclude '**/.venv' \
  --exclude '**/node_modules' \
  --exclude '**/build' \
  "$SRC/" "$PRIVATE_USER@$PRIVATE_HOST:$REPO_DIR/"

echo "=== running server tests ==="
ssh -p "$PRIVATE_PORT" "$PRIVATE_USER@$PRIVATE_HOST" \
  "cd $REPO_DIR/server && \
   if [ ! -d .venv ]; then python3 -m venv .venv && .venv/bin/pip -q install --upgrade pip; fi && \
   .venv/bin/pip -q install -r requirements.txt && \
   .venv/bin/python -m pytest tests -q"
