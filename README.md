# AutoOps 运维自动化平台

一个覆盖运维日常工作的全栈自动化平台：以 **CMDB 资产为底座**、**Ansible 为执行引擎**、**大模型为自然语言意图入口**，聚焦**巡检与批量作业**高频场景。

## 功能模块

| 模块 | 说明 |
|------|------|
| 资产管理 (CMDB) | 主机、主机组、标签、系统信息 |
| 作业中心 | 批量命令 / Playbook / 巡检执行，实时日志、结果统计 |
| 巡检中心 | 巡检模板库 + **AI 自然语言生成巡检脚本**（草稿→人工批准→执行） |
| 巡检计划 | **定时调度**（cron），自动执行巡检并生成报告，支持立即执行 |
| 巡检报告 | 每次巡检留痕，历史报告查询、健康度统计 |
| 告警通知 | 任务/巡检异常推送 webhook（钉钉/企微/通用） |
| 凭据管理 | SSH 密码/私钥 AES-256-GCM 加密存储，主机关联 |
| RBAC 权限 | admin / operator / viewer 三级角色，接口级鉴权 |
| 审计日志 | 登录、主机增删、任务执行、凭据操作全程留痕 |
| 执行引擎 | 可切换 `mock`（演示）/ `ansible`（真实）后端 |
| 大模型接入 | OpenAI 兼容接口（DeepSeek/通义/OpenAI 等），未配置时走 Mock |
| 认证 | JWT 登录，默认账号 admin/admin123 |

## 技术栈

- 后端：Python 3.13 + FastAPI + SQLAlchemy + SQLite（可切 PostgreSQL）
- 前端：React 18 + Ant Design 5 + Vite
- 执行：ansible-runner（预留）+ Mock 模拟
- 大模型：OpenAI 兼容 `chat/completions`

## 目录结构

```
backend/
  app/
    api/          # 路由（auth/hosts/tasks/inspections/plans/credentials/rbac）
    core/         # 配置、数据库、安全(JWT)、凭据加密(AES)
    models/       # SQLAlchemy 数据模型
    schemas/      # Pydantic 模型
    services/     # 大模型、调度器(APScheduler)、告警、审计
    executor/     # 执行引擎（mock/ansible）
  scripts/        # set_admin_password.py（重置密码）
  requirements.txt
frontend/
  src/
    api/          # axios 封装
    components/   # Layout
    pages/        # Login/Dashboard/Hosts/Tasks/Inspections/Plans/Security
```

## 部署

支持两种生产部署形态，完整步骤见 **[DEPLOY.md](DEPLOY.md)**：

| 方式 | 命令 | 访问地址 |
|------|------|---------|
| **Docker Compose** | `cp .env.docker.example .env`（填两个密钥）→ `docker compose up -d --build` | `http://<IP>:8080` |
| **Linux 裸机**（systemd + nginx） | `sudo bash deploy/install.sh` | `http://<IP>` |
| **Windows 本机**（单进程） | `start-prod.bat` | `http://<IP>:8000` |

```bash
# 最简 Docker 部署
cp .env.docker.example .env
# 改 SECRET_KEY / CREDENTIAL_SECRET（openssl rand -base64 48）
docker compose up -d --build
```

部署相关文件：

```
docker-compose.yml             # 前端 nginx + 后端（+ 可选 PostgreSQL profile）
.env.docker.example            # compose 环境变量模板
backend/Dockerfile             # 后端镜像（Python 3.12）
frontend/Dockerfile            # 前端镜像（多阶段构建，产物用 nginx 托管）
frontend/nginx.conf            # 容器内 nginx（SPA 回退 + /api 反代）
deploy/install.sh              # Linux 一键部署
deploy/systemd/*.service       # systemd 单元
deploy/nginx/autoops.conf      # 宿主机 nginx 配置
start-prod.bat                 # Windows 生产模式（单进程）
DEPLOY.md                      # 部署文档（含安全清单与排错）
```

> 生产上线前务必：改 admin 密码（`backend/scripts/set_admin_password.py`）、替换 `SECRET_KEY` / `CREDENTIAL_SECRET`、配置 HTTPS。清单见 DEPLOY.md 第 4 节。

## 本地开发启动

### 后端（已用 venv 隔离）

```bash
cd backend
python -m venv venv                  # 首次
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> 注意：本机若配置了 `http_proxy` 且导致 pip 卡死，请加 `--proxy ""` 直连安装。

### 前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

访问 http://localhost:5173 ，默认账号 `admin` / `admin123`。

## 配置（backend/.env）

复制 `.env.example` 为 `.env`，关键项：

```
EXECUTOR_BACKEND=mock        # mock 或 ansible
LLM_BASE_URL=                # 填写后启用真实大模型
LLM_API_KEY=
LLM_MODEL=
DATABASE_URL=sqlite:///./autoops.db   # 可切 PostgreSQL
CREDENTIAL_SECRET=           # 凭据加密密钥（生产必改，32 字节以上）
```

> 切换真实 Ansible：`EXECUTOR_BACKEND=ansible` 并 `pip install ansible-runner`。需确保目标机 SSH 免密或配置凭据。

## 已实现（P0 MVP）

- [x] 认证登录（JWT）
- [x] 主机/主机组增删查（CMDB）
- [x] 批量任务执行 + 结果统计 + 实时日志（mock 后端）
- [x] 巡检模板 CRUD + AI 自然语言生成脚本 + 草稿/批准流程
- [x] 巡检计划（cron 定时调度 + 立即执行）
- [x] 巡检报告（历史留痕 + 健康度）
- [x] 告警通知（webhook 占位：钉钉/企微/通用）
- [x] 凭据管理（AES-256-GCM 加密存储）
- [x] RBAC 多角色权限（admin/operator/viewer）
- [x] 审计日志（操作全程留痕）
- [x] 真实 ansible-runner 执行后端（可切换）
- [x] 前端管理后台（看板/资产/作业/巡检/巡检计划/安全审计）
- [x] 大模型 OpenAI 兼容接入（含 Mock 回退）

## 后续规划

- [ ] 巡检报告历史趋势图、看板图表增强
- [ ] 多租户、LDAP/SSO 登录
- [ ] 任务结果持久化到远端存储、分布式调度
