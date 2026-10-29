#!/usr/bin/env bash
# 一键：通过 GitHub API 创建仓库 + 推送到 GitHub
# 用法： ./push-to-github.sh <你的TOKEN> [仓库名]
# 示例： ./push-to-github.sh ghp_xxxxxxxx autoops-platform
set -euo pipefail

TOKEN="${1:-}"
REPO="${2:-autoops-platform}"

if [ -z "$TOKEN" ]; then
  echo "用法: ./push-to-github.sh <你的TOKEN> [仓库名]"
  echo "Token 生成: GitHub -> Settings -> Developer settings -> Personal access tokens -> Tokens (classic) -> Generate new token，勾选 repo 权限"
  exit 1
fi

API="https://api.github.com"
CURL="curl -s --noproxy * --max-time 30"

echo "[1/4] 校验 Token 并获取用户名..."
USER_JSON=$($CURL -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" "$API/user")
USER_LOGIN=$(echo "$USER_JSON" | grep -o '"login"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"login"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
if [ -z "$USER_LOGIN" ]; then
  echo "❌ Token 无效或无权访问。API 返回："
  echo "$USER_JSON" | head -5
  exit 1
fi
echo "    ✅ 已登录: $USER_LOGIN"

echo "[2/4] 创建公开仓库 $REPO ..."
CREATE_RES=$($CURL -X POST -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  "$API/user/repos" \
  -d "{\"name\":\"$REPO\",\"private\":false,\"description\":\"运维自动化平台 - Ansible批量执行 + AI自然语言巡检 + CMDB + RBAC + 审计\"}")
if echo "$CREATE_RES" | grep -q '"full_name"'; then
  echo "    ✅ 仓库已创建"
elif echo "$CREATE_RES" | grep -q 'already exists'; then
  echo "    ℹ️  仓库已存在，直接复用"
else
  echo "    ⚠️  创建返回：$(echo "$CREATE_RES" | head -c 300)"
fi

echo "[3/4] 配置 remote 并推送 ..."
REMOTE_URL="https://x-access-token:${TOKEN}@github.com/${USER_LOGIN}/${REPO}.git"
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_URL"
git push -u origin main

echo "[4/4] 清理 remote 中的 Token（安全）..."
git remote set-url origin "https://github.com/${USER_LOGIN}/${REPO}.git"

echo ""
echo "🎉 完成！仓库地址: https://github.com/${USER_LOGIN}/${REPO}"
