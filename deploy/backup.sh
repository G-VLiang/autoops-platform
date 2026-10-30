#!/usr/bin/env bash
# AutoOps 备份包装脚本（供 cron / systemd timer 调用）
#
# 用法：
#   ./deploy/backup.sh                              # 备份数据库
#   ./deploy/backup.sh --with-artifacts --keep 14   # 连产物一起备份，只留 14 份
#   ./deploy/backup.sh --list
#   ./deploy/backup.sh --restore 20261030-030000
#
# 环境变量：
#   APP_DIR  项目根目录（默认 /opt/autoops）
#   PY       解释器路径（默认 $APP_DIR/backend/venv/bin/python）
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/autoops}"
cd "$APP_DIR/backend"

if [ -n "${PY:-}" ]; then
  :
elif [ -x "./venv/bin/python" ]; then
  PY="./venv/bin/python"
elif [ -x "./.venv/bin/python" ]; then
  PY="./.venv/bin/python"
else
  PY="python3"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] backup start  app=$APP_DIR  py=$PY"
exec "$PY" scripts/backup.py "$@"
