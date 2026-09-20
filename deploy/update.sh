#!/usr/bin/env bash
# 生产机一键更新：拉 GitHub main，重建并启动 Compose。
# 本地试跑（不拉远程、不覆盖工作区）：
#   APP_DIR="$(pwd)" SKIP_GIT=1 bash deploy/update.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/LangChain_Demo}"
GIT_REMOTE="${GIT_REMOTE:-git@github.com:1525807864/Agent_Chat_RAG_Tools.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1/health}"

cd "$APP_DIR"

if [[ "${SKIP_GIT:-0}" != "1" ]]; then
  # GitHub HTTPS 在这台机器上会被重置，必须走 SSH
  git fetch "$GIT_REMOTE" "$GIT_BRANCH"
  git reset --hard FETCH_HEAD
fi

# .env 被 gitignore，reset 碰不到它
docker compose up -d --build
docker compose ps
curl -fsS -o /dev/null -w "health %{http_code}\n" "$HEALTH_URL"
