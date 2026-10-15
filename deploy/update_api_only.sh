#!/usr/bin/env bash
# 小内存机安全更新：拉 main → 构建 sandbox + api → 启动（默认不重建 nginx/前端）。
#需要重建前端时：REBUILD_WEB=1 bash deploy/update_api_only.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/LangChain_Demo}"
GIT_REMOTE="${GIT_REMOTE:-git@github.com:1525807864/Agent_Chat_RAG_Tools.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1/health}"
REBUILD_WEB="${REBUILD_WEB:-0}"

cd "$APP_DIR"

if [[ "${SKIP_GIT:-0}" != "1" ]]; then
  git fetch "$GIT_REMOTE" "$GIT_BRANCH"
  git reset --hard FETCH_HEAD
fi

mkdir -p "${SANDBOX_WORKSPACE_HOST:-$APP_DIR/data/sandbox}"

echo "==> build sandbox-image"
docker compose --profile build build sandbox-image

echo "==> build api"
docker compose build api

if [[ "$REBUILD_WEB" == "1" ]]; then
  echo "==> build nginx (frontend) — may take long on 2G hosts"
  docker compose build nginx
  docker compose up -d
else
  echo "==> up -d without rebuilding nginx (use existing web image)"
  docker compose up -d --no-deps api
  docker compose up -d
fi

docker compose ps
curl -fsS -o /dev/null -w "health %{http_code}\n" "$HEALTH_URL" || true
docker compose exec -T holmes curl -fsS -o /dev/null -w "holmes health %{http_code}\n" \
  http://127.0.0.1:5050/healthz || true
docker image inspect nexora-sandbox:latest >/dev/null
echo "deploy ok (api+sandbox; web rebuild=${REBUILD_WEB})"
docker compose logs --tail 30 api
