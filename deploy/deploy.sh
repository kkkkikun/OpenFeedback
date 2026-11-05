#!/usr/bin/env bash
# Deploy OpenFeedback to the target server.
#
#   OF_DEPLOY_HOST=8.160.116.34 OF_DEPLOY_PORT=55971 OF_DEPLOY_USER=root \
#   OF_PUBLIC_HOST=https://8.160.116.34 ./deploy/deploy.sh
#
# The script is idempotent: it syncs the code, refreshes .env (keeping the
# existing secrets), rebuilds the image, and restarts the stack.
set -euo pipefail

HOST="${OF_DEPLOY_HOST:?set OF_DEPLOY_HOST}"
PORT="${OF_DEPLOY_PORT:-22}"
USER="${OF_DEPLOY_USER:-root}"
REMOTE_DIR="${OF_DEPLOY_DIR:-/opt/openfeedback}"
PUBLIC_HOST="${OF_PUBLIC_HOST:?set OF_PUBLIC_HOST}"
ACME_EMAIL="${ACME_EMAIL:-admin@example.com}"
CADDY_VERSION="${OF_CADDY_VERSION:-2.11.4}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SSH=(ssh -p "$PORT" -o StrictHostKeyChecking=accept-new "$USER@$HOST")
RSYNC=(rsync -az --delete -e "ssh -p $PORT")

echo "=== [1/6] syncing code -> $USER@$HOST:$REMOTE_DIR ==="
"${SSH[@]}" "mkdir -p '$REMOTE_DIR'"
"${RSYNC[@]}" \
  --exclude '.git' \
  --exclude '.ssh_helper.py' \
  --exclude '**/__pycache__' \
  --exclude '**/.venv' \
  --exclude '**/node_modules' \
  --exclude '**/build' \
  --exclude 'deploy/.env' \
  --exclude 'deploy/.cache' \
  "$REPO_DIR/" "$USER@$HOST:$REMOTE_DIR/"

echo "=== [2/6] preparing .env ==="
# The heredoc is quoted so nothing is expanded locally; the values the
# remote side needs arrive as positional arguments.
"${SSH[@]}" bash -s -- "$PUBLIC_HOST" "$ACME_EMAIL" "$REMOTE_DIR" <<'REMOTE'
set -euo pipefail
PUBLIC_HOST="$1"
ACME_EMAIL="$2"
cd "$3/deploy"
if [ ! -f .env ]; then
  ADMIN_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
  IP_SALT="$(openssl rand -hex 32)"
  cat > .env <<EOF
OF_ADMIN_USERNAME=admin
OF_ADMIN_PASSWORD=$ADMIN_PASSWORD
OF_BASE_URL=$PUBLIC_HOST
OF_TRUSTED_PROXY_HEADERS=true
OF_MAX_ATTACHMENT_BYTES=2097152
OF_MAX_ATTACHMENTS=3
OF_SUBMISSIONS_PER_HOUR=10
OF_COOKIE_SECURE=true
OF_SESSION_TTL_HOURS=12
OF_IP_HASH_SALT=$IP_SALT
OF_PUBLIC_HOST=$PUBLIC_HOST
ACME_EMAIL=$ACME_EMAIL
EOF
  chmod 600 .env
  echo "--- admin password (shown once) ---"
  echo "$ADMIN_PASSWORD"
else
  echo ".env exists; keeping the existing secrets"
  grep -q '^OF_PUBLIC_HOST=' .env || echo "OF_PUBLIC_HOST=$PUBLIC_HOST" >> .env
  grep -q '^ACME_EMAIL=' .env || echo "ACME_EMAIL=$ACME_EMAIL" >> .env
fi
REMOTE
echo "=== [3/6] publishing the SDK's Maven repository ==="
# The SDK artifacts are built on the build host and copied here, so a host
# app can depend on them from the same URL it uses for the service.
MAVEN_SRC="${OF_MAVEN_REPO_SRC:-$REPO_DIR/android-sdk/maven-repo}"
if [ -d "$MAVEN_SRC" ] && [ -n "$(ls -A "$MAVEN_SRC" 2>/dev/null)" ]; then
  "${SSH[@]}" "mkdir -p '$REMOTE_DIR/android-sdk/maven-repo'"
  rsync -az --delete -e "ssh -p $PORT" \
    "$MAVEN_SRC/" "$USER@$HOST:$REMOTE_DIR/android-sdk/maven-repo/"
  echo "maven repository synced"
else
  echo "no local maven repository at $MAVEN_SRC; skipping" >&2
  echo "build the SDK first: ./gradlew publishReleasePublicationToLocalMavenRepository" >&2
fi

echo "=== [4/6] fetching the Caddy release and building the images ==="
# Caddy is fetched on the host, because the container build may have no
# route to GitHub or to a package mirror.
"${SSH[@]}" bash -s -- "$REMOTE_DIR" "$CADDY_VERSION" <<'REMOTE'
set -euo pipefail
REMOTE_DIR="$1"
CADDY_VERSION="$2"
CACHE="$REMOTE_DIR/deploy/.cache"
mkdir -p "$CACHE"
TARBALL="$CACHE/caddy.tar.gz"
if [ ! -s "$TARBALL" ]; then
  echo "downloading caddy $CADDY_VERSION"
  curl -fsSL --retry 3 \
    "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz" \
    -o "$TARBALL"
fi
ls -lh "$TARBALL"
REMOTE

"${SSH[@]}" "cd $REMOTE_DIR/deploy && docker compose build --pull api caddy"

echo "=== [5/6] starting the stack ==="
"${SSH[@]}" "cd $REMOTE_DIR/deploy && docker compose up -d && docker compose ps"

echo "=== [6/6] waiting for the service to answer ==="
# The API is not published on the host, so it is checked from inside the
# compose network.
for attempt in $(seq 1 30); do
  if "${SSH[@]}" "cd $REMOTE_DIR/deploy && docker compose exec -T api python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=4)\"" >/dev/null 2>&1; then
    echo "the API is up"
    break
  fi
  if [ "$attempt" = "30" ]; then
    echo "the API did not become healthy" >&2
    "${SSH[@]}" "cd $REMOTE_DIR/deploy && docker compose logs --tail=60" >&2
    exit 1
  fi
  sleep 2
done

# The public URL only answers once Caddy holds a certificate. That needs
# ports 80 and 443 to be reachable from the internet, so a failure here is
# reported but does not fail the deployment.
if "${SSH[@]}" "curl -fsS --max-time 10 '$PUBLIC_HOST/api/v1/health'" >/dev/null 2>&1; then
  echo "public URL is serving: $PUBLIC_HOST"
else
  echo "the public URL is not serving yet." >&2
  echo "Caddy needs inbound TCP 80 and 443 reachable from the internet" >&2
  echo "to obtain its certificate. It retries on its own once they are open." >&2
  echo "current certificate state:" >&2
  "${SSH[@]}" "cd $REMOTE_DIR/deploy && docker compose logs caddy 2>&1 | tail -5" >&2
fi

echo "=== deploy finished: $PUBLIC_HOST ==="
