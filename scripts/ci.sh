#!/usr/bin/env bash
# The checks CI runs, runnable locally with the same commands:
#
#   scripts/ci.sh            # everything
#   scripts/ci.sh backend    # lint, tests, dependency audit
#   scripts/ci.sh mobile     # lint, full iOS bundle
#   scripts/ci.sh docker     # build the backend image and check that it starts healthy
#
# Locally the backend uses backend/.venv when it exists; in CI the tools are on the PATH.
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

backend() {
  (
    cd backend
    if [[ -d .venv ]]; then PATH="$PWD/.venv/bin:$PATH"; fi
    step "backend: ruff"
    ruff check .
    step "backend: pytest"
    pytest -q
    step "backend: pip-audit (known vulnerabilities in runtime dependencies)"
    pip-audit -r requirements.txt --progress-spinner off
  )
}

mobile() {
  (
    cd mobile
    [[ -d node_modules ]] || npm ci
    step "mobile: eslint"
    npx eslint . --max-warnings 0
    step "mobile: bundle the iOS app with Metro"
    out="$(mktemp -d)"
    trap 'rm -rf "$out"' EXIT
    CI=1 npx expo export --platform ios --output-dir "$out" >/dev/null
    echo "bundle ok"
  )
}

docker_smoke() {
  step "docker: build"
  docker build -t virtual-coach-backend:ci backend
  step "docker: start and wait for /health"
  # Dummy settings: the health check needs no external service.
  id="$(docker run -d -p 127.0.0.1:18000:8000 -e OPENAI_API_KEY=ci -e STRAVA_CLIENT_ID=0 \
        -e STRAVA_CLIENT_SECRET=ci virtual-coach-backend:ci)"
  trap 'docker rm -f "$id" >/dev/null' EXIT
  for _ in $(seq 30); do
    if curl -fsS http://127.0.0.1:18000/health >/dev/null 2>&1; then echo "healthy"; return 0; fi
    sleep 1
  done
  docker logs "$id"
  echo "container did not become healthy" >&2
  return 1
}

case "${1:-all}" in
  backend) backend ;;
  mobile) mobile ;;
  docker) docker_smoke ;;
  all) backend; mobile; docker_smoke ;;
  *) echo "usage: $0 [backend|mobile|docker|all]" >&2; exit 2 ;;
esac
