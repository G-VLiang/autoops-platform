#!/usr/bin/env bash
# AutoOps 本地（裸机 / 云主机）一键部署脚本 —— Linux
#
# 用法：
#   sudo bash deploy/install.sh              # 完整部署（venv + 构建前端 + systemd + nginx）
#   sudo WEB_PORT=8080 bash deploy/install.sh
#   bash deploy/install.sh --app-only        # 非 root / 不装服务，只准备运行环境
#
# 可选环境变量：
#   WEB_PORT=80            对外端口
#   SERVER_NAME=_          nginx server_name（有域名就填域名）
#   PYTHON_BIN=python3     指定 Python 解释器（需 3.10+）
#   RUN_USER=autoops       服务运行用户（默认当前用户）
#   PIP_EXTRA_ARGS=""      pip 额外参数，如 '--proxy= -i https://pypi.tuna.tsinghua.edu.cn/simple'
#   REBUILD=1              强制重新构建前端

set -euo pipefail
trap 'printf "\033[1;31m[autoops]\033[0m 第 %s 行执行失败，请查看上方输出\n" "$LINENO" >&2' ERR

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_PORT="${WEB_PORT:-80}"
SERVER_NAME="${SERVER_NAME:-_}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_USER="${RUN_USER:-$(id -un)}"
APP_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --app-only) APP_ONLY=1 ;;
    *) echo "未知参数: $arg"; exit 1 ;;
  esac
done

log()  { printf '\033[1;32m[autoops]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[autoops]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[autoops]\033[0m %s\n' "$*" >&2; exit 1; }

log "项目目录: $APP_DIR"

# ---------- 1. 后端虚拟环境 ----------
command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "未找到 $PYTHON_BIN，请先安装 Python 3.10+"
"$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
  || die "Python 版本过低，需要 3.10+"

if [ ! -x "$APP_DIR/backend/venv/bin/python" ]; then
  log "创建虚拟环境 backend/venv ..."
  "$PYTHON_BIN" -m venv "$APP_DIR/backend/venv"
fi

log "安装后端依赖 ..."
# shellcheck disable=SC2086
"$APP_DIR/backend/venv/bin/python" -m pip install --upgrade pip -q ${PIP_EXTRA_ARGS:-}
# shellcheck disable=SC2086
"$APP_DIR/backend/venv/bin/python" -m pip install -q -r "$APP_DIR/backend/requirements.txt" ${PIP_EXTRA_ARGS:-}

# ---------- 2. 生成 .env（含随机密钥）----------
if [ ! -f "$APP_DIR/backend/.env" ]; then
  log "生成 backend/.env 并写入随机密钥 ..."
  SECRET=$("$APP_DIR/backend/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))')
  CRED=$("$APP_DIR/backend/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))')
  cat > "$APP_DIR/backend/.env" <<EOF
# 由 deploy/install.sh 生成于 $(date '+%Y-%m-%d %H:%M:%S')
DATABASE_URL=sqlite:///$APP_DIR/backend/autoops.db
SECRET_KEY=$SECRET
CREDENTIAL_SECRET=$CRED
EXECUTOR_BACKEND=mock
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
CORS_ORIGINS=http://localhost:$WEB_PORT,http://127.0.0.1:$WEB_PORT
EOF
  chmod 600 "$APP_DIR/backend/.env"
else
  warn "backend/.env 已存在，保留原配置（不会覆盖你的密钥）"
fi

# ---------- 3. 前端构建 ----------
if [ "${REBUILD:-0}" = "1" ] || [ ! -f "$APP_DIR/frontend/dist/index.html" ]; then
  if command -v npm >/dev/null 2>&1; then
    log "构建前端（npm ci && npm run build）..."
    ( cd "$APP_DIR/frontend" && npm ci --no-audit --no-fund && npm run build )
  else
    warn "未找到 npm，跳过前端构建。请在有 Node.js 的机器执行 cd frontend && npm ci && npm run build"
    warn "或直接用后端单进程模式（uvicorn 会自动托管 frontend/dist）"
  fi
else
  log "前端 dist 已存在，跳过构建（强制重建：REBUILD=1 bash deploy/install.sh）"
fi

# ---------- 4. systemd 服务 ----------
if [ "$APP_ONLY" = "1" ]; then
  warn "--app-only：跳过 systemd / nginx 安装"
elif [ "$(id -u)" -ne 0 ]; then
  warn "非 root 用户，跳过 systemd / nginx 安装。手动启动方式："
  warn "  cd $APP_DIR/backend && ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"
elif ! command -v systemctl >/dev/null 2>&1; then
  warn "未检测到 systemd，跳过服务注册"
else
  log "注册 systemd 服务 autoops-backend ..."
  sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__RUN_USER__|$RUN_USER|g" \
      "$APP_DIR/deploy/systemd/autoops-backend.service" > /etc/systemd/system/autoops-backend.service
  systemctl daemon-reload
  systemctl enable autoops-backend >/dev/null 2>&1 || true
  systemctl restart autoops-backend
  sleep 2
  if systemctl is-active --quiet autoops-backend; then
    log "后端已启动（systemctl status autoops-backend 查看日志）"
  else
    warn "后端启动失败，请执行：journalctl -u autoops-backend -n 50 --no-pager"
  fi
fi

# ---------- 5. nginx ----------
if [ "$APP_ONLY" = "0" ] && [ "$(id -u)" -eq 0 ] && command -v nginx >/dev/null 2>&1; then
  log "配置 nginx（端口 $WEB_PORT）..."
  TMP_CONF="$(mktemp)"
  sed -e "s|__APP_DIR__|$APP_DIR|g" \
      -e "s|__WEB_PORT__|$WEB_PORT|g" \
      -e "s|__SERVER_NAME__|$SERVER_NAME|g" \
      "$APP_DIR/deploy/nginx/autoops.conf" > "$TMP_CONF"

  if [ -d /etc/nginx/sites-available ]; then
    install -m 644 "$TMP_CONF" /etc/nginx/sites-available/autoops
    ln -sf /etc/nginx/sites-available/autoops /etc/nginx/sites-enabled/autoops
  else
    install -m 644 "$TMP_CONF" /etc/nginx/conf.d/autoops.conf
  fi
  rm -f "$TMP_CONF"

  if nginx -t 2>/dev/null; then
    systemctl reload nginx || nginx -s reload
    log "nginx 已加载配置"
  else
    warn "nginx 配置校验失败，请执行 nginx -t 查看原因"
  fi
elif [ "$APP_ONLY" = "0" ]; then
  warn "未安装 nginx，跳过。装好后执行：apt install -y nginx（或 yum install -y nginx）再重跑本脚本"
fi

# ---------- 完成 ----------
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
log "部署完成"
echo "  访问地址: http://${IP:-服务器IP}${WEB_PORT:+:$WEB_PORT}"
echo "  默认账号: admin / admin123  （务必立即修改，见 DEPLOY.md）"
echo "  配置文件: $APP_DIR/backend/.env"
echo "  后端日志: journalctl -u autoops-backend -f"
