#!/usr/bin/env bash
set -Eeuo pipefail

deploy_root="${DEPLOY_ROOT:-/opt/global-meeting}"
backend_dir="$deploy_root/backend"
frontend_dir="$deploy_root/frontend"
compose_file="$backend_dir/docker-compose.production.yml"
lock_file="$deploy_root/.deploy.lock"
state_file="$deploy_root/.last-successful-deployment"

for required_path in \
  "$backend_dir/.git" \
  "$frontend_dir/.git" \
  "$backend_dir/.env" \
  "$compose_file"; do
  if [[ ! -e "$required_path" ]]; then
    echo "Required deployment path is missing: $required_path" >&2
    exit 1
  fi
done

exec 9>"$lock_file"
if ! flock -w 900 9; then
  echo "Another deployment did not finish within 15 minutes." >&2
  exit 1
fi

update_repository() {
  local repository_dir="$1"

  if [[ -n "$(git -C "$repository_dir" status --porcelain --untracked-files=no)" ]]; then
    echo "Tracked files are modified in $repository_dir; deployment stopped." >&2
    exit 1
  fi

  git -C "$repository_dir" switch main
  git -C "$repository_dir" pull --ff-only origin main
}

update_repository "$backend_dir"
update_repository "$frontend_dir"

backend_sha="$(git -C "$backend_dir" rev-parse HEAD)"
frontend_sha="$(git -C "$frontend_dir" rev-parse HEAD)"
export IMAGE_TAG="${backend_sha:0:12}-${frontend_sha:0:12}"

compose=(
  docker compose
  --env-file "$backend_dir/.env"
  --file "$compose_file"
)

"${compose[@]}" config --quiet
"${compose[@]}" build
"${compose[@]}" up -d db
"${compose[@]}" run --rm backend alembic upgrade head
"${compose[@]}" up -d backend frontend

for attempt in {1..30}; do
  if curl --fail --silent --show-error --max-time 5 \
    http://127.0.0.1/health >/dev/null; then
    state_tmp="$state_file.tmp.$$"
    printf 'backend=%s\nfrontend=%s\n' "$backend_sha" "$frontend_sha" >"$state_tmp"
    mv "$state_tmp" "$state_file"
    "${compose[@]}" ps
    echo "Deployment completed: backend=$backend_sha frontend=$frontend_sha"
    exit 0
  fi
  sleep 2
done

"${compose[@]}" ps
"${compose[@]}" logs --tail 100 backend frontend
echo "Deployment health check failed." >&2
exit 1
