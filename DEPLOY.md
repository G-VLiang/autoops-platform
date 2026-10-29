# 部署指南

本项目支持两种部署形态，另有开发模式（见 [README](README.md)）：

| 方式 | 适合场景 | 组成 | 复杂度 |
|------|---------|------|--------|
| **A. Docker Compose** | 生产/试用、想一条命令起全栈 | 前端 nginx 容器 + 后端容器（+ 可选 PostgreSQL） | ★ |
| **B. 本地系统直接部署** | 已有服务器、想少一层容器、要接真实 Ansible | systemd 托管 uvicorn + nginx 托管前端（Linux）；Windows 单进程 | ★★ |

两种方式用的都是**同一份代码、同一套环境变量**，可以随时切换。

## 验证状态（哪些实际跑过）

| 项 | 状态 |
|----|------|
| `requirements.txt` 全量安装 + 全新虚拟环境启动应用 | ✅ 已在干净 venv 实测（模拟容器首次启动） |
| 单进程模式（后端托管前端、SPA 深链接、API 不被吞、静态文件） | ✅ 已实测 |
| `start-prod.bat` 逻辑 | ✅ 逻辑与已验证的单进程模式一致 |
| `docker-compose.yml` / 两个 Dockerfile | ⚠️ 本机未装 Docker，**未实际构建**；YAML 已校验，依赖安装步骤已用干净环境等效验证 |
| `deploy/install.sh`（Linux） | ⚠️ 本机是 Windows，无法执行，仅做语法检查；systemd/nginx 片段为标准写法 |

---

## 0. 前置条件

| 项 | Docker 方式 | 本地方式 |
|----|------------|---------|
| 系统 | Linux（推荐）/ macOS / Windows + Docker Desktop | Linux（systemd）/ Windows |
| Docker | 24+ 且 `docker compose` v2 | 不需要 |
| Python | 镜像内置 | 3.10+（推荐 3.12） |
| Node.js | 镜像内置 | 18+，**仅构建前端时**需要 |
| nginx | 镜像内置 | 需要（也可不用，用单进程模式） |
| 端口 | `8080`（可改） | `80`（页面）+ `8000`（后端，仅本机） |

> 说明：容器镜像里 Python 用的是 **3.12**，不是本地的 3.13。原因是 `passlib 1.7.4` 依赖 `bcrypt 4.0.1`，该版本没有 cp313 预编译包，3.13 下需要现场编译 Rust，容易失败。

---

## A. Docker Compose 部署

### A1. 准备配置

```bash
git clone https://github.com/G-VLiang/autoops-platform.git
cd autoops-platform

cp .env.docker.example .env

# 生成两个密钥并填进 .env（必做，否则 compose 会拒绝启动）
openssl rand -base64 48     # -> SECRET_KEY
openssl rand -base64 32     # -> CREDENTIAL_SECRET
```

`.env` 里必须改的两行：

```ini
SECRET_KEY=你生成的第一个值
CREDENTIAL_SECRET=你生成的第二个值
```

### A2. 启动

```bash
docker compose up -d --build
docker compose ps          # 等 backend 变成 healthy
```

打开 `http://<服务器IP>:8080`，账号 `admin` / `admin123`。

### A3. 架构说明

```
浏览器 :8080
   │
   ▼
frontend 容器（nginx）
   ├── /            → /usr/share/nginx/html（React 构建产物，SPA 路由回退）
   ├── /assets/     → 静态资源，缓存 30 天
   └── /api/  /health → 反向代理到 backend:8000（容器内网，不对外暴露）
                            │
                            ▼
                     backend 容器（uvicorn，单 worker）
                            ├── SQLite：卷 autoops-data → /app/data/autoops.db
                            └── APScheduler：巡检计划定时触发
```

- 后端**不映射宿主端口**，只走容器内网，安全面更小。
- SQLite 数据存在 named volume `autoops-data`，`docker compose down` 不会丢，`down -v` 才会删。

### A4. 常用运维命令

```bash
docker compose logs -f backend        # 后端日志
docker compose logs -f frontend       # nginx 访问日志
docker compose restart backend        # 重启后端（改 .env 后需要）
docker compose down                   # 停止（保留数据）
docker compose up -d --build          # 改代码后重新构建启动
```

### A5. 切 PostgreSQL

```bash
# 1. .env 里改 DATABASE_URL
#    DATABASE_URL=postgresql+psycopg2://autoops:autoops@postgres:5432/autoops
# 2. 带 profile 启动
docker compose --profile postgres up -d --build
```

### A6. 需要真实执行 Ansible 时

```bash
# .env
EXECUTOR_BACKEND=ansible
INSTALL_ANSIBLE=true
```

```bash
docker compose up -d --build
# 把 SSH 私钥挂进容器（compose 里给 backend 加一行 volume）：
#   - ~/.ssh/id_rsa:/root/.ssh/id_rsa:ro
```

> 容器内跑 Ansible 需要能连到目标机，且私钥权限为 600。若嫌麻烦，用本地部署方式更顺。

### A7. 对公网暴露 / HTTPS

compose 默认只开 HTTP。生产建议在宿主机再放一层反向代理（或用 Caddy/Traefik）做证书，然后：

```ini
# .env
CORS_ORIGINS=https://ops.example.com
```

---

## B. 本地系统直接部署

### B1. Linux 一键部署（推荐）

```bash
git clone https://github.com/G-VLiang/autoops-platform.git
cd autoops-platform

sudo bash deploy/install.sh
# 自定义端口：sudo WEB_PORT=8080 bash deploy/install.sh
# 有域名：   sudo SERVER_NAME=ops.example.com bash deploy/install.sh
```

脚本会依次完成：

1. 创建 `backend/venv` 并安装依赖
2. 生成 `backend/.env`（**自动写入随机 SECRET_KEY / CREDENTIAL_SECRET**，权限 600）
3. `npm ci && npm run build` 构建前端到 `frontend/dist`
4. 注册 systemd 服务 `autoops-backend` 并启动
5. 写入 nginx 配置并 reload（自动适配 `sites-available` 或 `conf.d`）

完成后访问 `http://<服务器IP>`。

> 没有 Node.js 的机器：先在别处构建好 `frontend/dist` 再拷过来，或用下面的「单进程模式」。

### B2. Linux 手动部署（想自己控制每一步）

```bash
# 1. 后端环境
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 2. 配置
cp .env.example .env
# 编辑 .env：SECRET_KEY、CREDENTIAL_SECRET 必须改成随机值
python3 -c "import secrets;print(secrets.token_urlsafe(48))"

# 3. 前端构建
cd ../frontend && npm ci && npm run build

# 4. 后端常驻（systemd）
sudo cp ../deploy/systemd/autoops-backend.service /etc/systemd/system/
sudo sed -i "s|__APP_DIR__|$(cd .. && pwd)|g; s|__RUN_USER__|$(whoami)|g" /etc/systemd/system/autoops-backend.service
sudo systemctl daemon-reload && sudo systemctl enable --now autoops-backend

# 5. nginx
sudo cp ../deploy/nginx/autoops.conf /etc/nginx/conf.d/autoops.conf
sudo sed -i "s|__APP_DIR__|$(cd .. && pwd)|g; s|__WEB_PORT__|80|g; s|__SERVER_NAME__|_|g" /etc/nginx/conf.d/autoops.conf
sudo nginx -t && sudo systemctl reload nginx
```

### B3. 单进程模式（不用 nginx、不用 Docker）

前端构建产物放在 `frontend/dist` 时，**后端会自动托管前端页面**（`app/main.py` 的 `_mount_frontend`），一个端口就能对外服务：

```bash
cd backend
./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
# 浏览器访问 http://<IP>:8000
```

### B4. Windows 本机部署

```bat
start-prod.bat
```

脚本会：`frontend\dist` 不存在则先构建 → 启动 `uvicorn` 监听 `0.0.0.0:8000`（同时提供 API 和页面）。

访问 `http://localhost:8000`。

**要开机自启/后台常驻**，二选一：

- **NSSM**（推荐）：`nssm install AutoOps` → Path 选 `D:\...\backend\venv\Scripts\uvicorn.exe`，Arguments 填 `app.main:app --host 0.0.0.0 --port 8000 --workers 1`，Startup directory 填 `D:\...\backend`
- **任务计划程序**：创建任务 → 触发器「计算机启动时」→ 操作指向 `start-prod.bat` → 勾选「不管用户是否登录都要运行」

> 开发模式（热更新）仍用 `start.bat`，端口 5173，仅本机调试用，不要对外暴露。

---

## 3. 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `DATABASE_URL` | `sqlite:///./autoops.db` | Docker 内为 `sqlite:////app/data/autoops.db`；PostgreSQL 填 `postgresql+psycopg2://user:pass@host:5432/db` |
| `SECRET_KEY` | `dev-secret-change-me` | JWT 签名密钥，**生产必改** |
| `CREDENTIAL_SECRET` | 开发默认值 | 凭据 AES-256-GCM 加密密钥，**生产必改，≥32 字节** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | 登录态有效期（分钟） |
| `EXECUTOR_BACKEND` | `mock` | `mock` 模拟 / `ansible` 真实执行 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 空 | OpenAI 兼容接口；留空则 AI 生成走内置模板 |
| `CORS_ORIGINS` | `http://localhost:5173,...` | 允许的跨域来源，逗号分隔 |
| `WEB_PORT` | `8080` / `80` | 仅 compose 与 install.sh 使用 |

> 启动时会自检：若 `SECRET_KEY` / `CREDENTIAL_SECRET` 仍是默认值，日志会打印 `[安全告警]`。看到就说明还没配好。

---

## 4. 上线前必做清单

| # | 事项 | 怎么做 |
|---|------|--------|
| 1 | 改 admin 密码 | `cd backend && ./venv/bin/python scripts/set_admin_password.py admin '新密码'`（Windows 用 `venv\Scripts\python.exe`） |
| 2 | 换掉两个密钥 | `openssl rand -base64 48` 生成后写入 `.env`，重启生效 |
| 3 | 只暴露必要端口 | 后端 8000 不对外；Docker 方式后端本来就只在容器内网 |
| 4 | 配 HTTPS | 前置 Caddy/Nginx + 证书；同时把 `CORS_ORIGINS` 改成 https 域名 |
| 5 | 规划备份 | SQLite 直接备份 `.db` 文件；PostgreSQL 用 `pg_dump` |
| 6 | 收紧 RBAC | 日常用 `operator`，`viewer` 只读；不要所有人共用 admin |
| 7 | 限制访问来源 | 云安全组/防火墙只放行 80/443，别把 8000 开公网 |
| 8 | 盯日志 | `journalctl -u autoops-backend -f` 或 `docker compose logs -f backend` |

---

## 5. 升级与回滚

**Docker：**

```bash
git pull
docker compose up -d --build          # 重建镜像并滚动重启
docker compose logs -f backend        # 确认无异常
```

**本地：**

```bash
git pull
cd backend && ./venv/bin/pip install -r requirements.txt
cd ../frontend && npm ci && npm run build
sudo systemctl restart autoops-backend && sudo systemctl reload nginx
```

> 回滚：`git checkout <上一个 commit>` 后重复上面的构建步骤；数据库结构如有变更，先备份 `.db` 文件。

**备份 SQLite：**

```bash
# Docker
docker compose exec backend cp /app/data/autoops.db /app/data/backup-$(date +%F).db
# 本地
cp backend/autoops.db backend/autoops-$(date +%F).db
```

---

## 6. 常见问题

**Q: `pip install` 卡住不动 / 被 kill**
这台机器（或服务器）如果配了 `http_proxy`，pip 会走代理导致超时。加 `--proxy ""` 直连：

```bash
pip install --proxy "" -r requirements.txt
# 或国内加速
pip install --proxy "" -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

Docker 镜像里已经显式清空了代理变量，不会踩这个坑。

**Q: 页面能打开，但刷新 `/plans` 就 404**
nginx 少了 SPA 回退。确认配置里有 `try_files $uri $uri/ /index.html;`（本项目的两份配置都已包含）。

**Q: 巡检计划被重复执行**
`--workers` 必须为 **1**。调度器在进程内，多个 worker 会各自注册一份计划。Dockerfile 和 systemd unit 都已固定为 1。

**Q: `database is locked`**
SQLite 在并发写多时有此问题。多人使用或任务频繁时切 PostgreSQL（compose 已内置 `postgres` profile）。

**Q: 改了模型字段，启动报 `no such column`**
`create_all` 不会给已存在的表加列。开发期可删库重建；生产请手工 `ALTER TABLE` 或引入 Alembic 迁移。

**Q: 启动后日志打印 `[安全告警] SECRET_KEY 仍是默认值`**
`.env` 没生效或没配。注意 `.env` 必须放在 **`backend/` 目录**（systemd 的 `WorkingDirectory` 已指向那里）。

**Q: 容器起不来，提示 `SECRET_KEY` 未设置**
compose 故意做了强校验。复制 `.env.docker.example` 为 `.env` 并填值。

**Q: 时间不对（巡检计划按错误时区触发）**
设置 `TZ=Asia/Shanghai`（compose 和 systemd 都已默认设置）。
