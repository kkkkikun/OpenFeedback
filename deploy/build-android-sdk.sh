#!/usr/bin/env bash
# Build and test the OpenFeedback Android SDK on the private build host.
#
# The host needs the Android SDK (ANDROID_HOME) and a JDK 17. Both are set up
# by deploy/setup-build-host.sh.
set -euo pipefail

REPO_DIR="${OF_REPO_DIR:-$HOME/work/OpenFeedback}"
PRIVATE_HOST="${OF_PRIVATE_HOST:-172.16.38.110}"
PRIVATE_PORT="${OF_PRIVATE_PORT:-56127}"
PRIVATE_USER="${OF_PRIVATE_USER:-kikun}"
TASK="${1:-assemble}"

echo "=== rsync repo -> $PRIVATE_HOST:$REPO_DIR ==="
rsync -az --delete \
  -e "ssh -p $PRIVATE_PORT" \
  --exclude '.git' \
  --exclude '.ssh_helper.py' \
  --exclude '**/__pycache__' \
  --exclude '**/.venv' \
  --exclude '**/node_modules' \
  --exclude '**/build' \
  --exclude '**/.gradle' \
  "$SRC/" "$PRIVATE_USER@$PRIVATE_HOST:$REPO_DIR/"

echo "=== gradle $TASK ==="
ssh -p "$PRIVATE_PORT" "$PRIVATE_USER@$PRIVATE_HOST" bash -s -- "$REPO_DIR" "$TASK" <<'REMOTE'
set -euo pipefail
REPO_DIR="$1"
TASK="$2"
source "$HOME/.of-build-env"
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
cd "$REPO_DIR/android-sdk"
./gradlew --no-daemon "$TASK" --stacktrace
REMOTE
