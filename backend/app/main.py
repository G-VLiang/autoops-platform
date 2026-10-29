"""应用入口。"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.api import api_router

logger = logging.getLogger("autoops")

# 建表
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}


def init_seed():
    """初始化默认管理员账号与演示数据。"""
    from app.models import User, HostGroup, Host, InspectionTemplate
    from app.core.security import hash_password

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "admin").first():
            db.add(User(username="admin", hashed_password=hash_password("admin123"), role="admin"))

        if not db.query(HostGroup).filter(HostGroup.name == "生产环境").first():
            g = HostGroup(name="生产环境", description="生产服务器组")
            db.add(g)
            db.flush()
            demo_hosts = [
                Host(hostname="web-01", ip="192.168.1.10", os_type="linux", os_version="CentOS 7.9", group_id=g.id, tags=["web"]),
                Host(hostname="web-02", ip="192.168.1.11", os_type="linux", os_version="CentOS 7.9", group_id=g.id, tags=["web"]),
                Host(hostname="db-01", ip="192.168.1.20", os_type="linux", os_version="Ubuntu 22.04", group_id=g.id, tags=["db", "mysql"]),
                Host(hostname="cache-01", ip="192.168.1.30", os_type="linux", os_version="Debian 11", group_id=g.id, tags=["redis"]),
            ]
            db.add_all(demo_hosts)

        if not db.query(InspectionTemplate).first():
            db.add(InspectionTemplate(
                name="系统基础巡检",
                description="CPU/内存/磁盘/负载基础巡检",
                category="custom",
                status="approved",
                generated_by_llm=False,
                playbook="""---
- name: 系统基础巡检
  hosts: all
  gather_facts: true
  tasks:
    - name: 检查磁盘使用率
      ansible.builtin.shell: df -h
      register: df_result
      changed_when: false
    - name: 检查内存
      ansible.builtin.shell: free -m
      register: mem_result
      changed_when: false
    - name: 检查负载
      ansible.builtin.shell: uptime
      register: load_result
      changed_when: false
""",
            ))

        db.commit()
    finally:
        db.close()


def _check_insecure_defaults():
    """生产部署自检：密钥仍是开发默认值时给出醒目告警。"""
    problems = []
    if settings.SECRET_KEY in ("dev-secret-change-me", ""):
        problems.append("SECRET_KEY 仍是默认值（JWT 可被伪造）")
    if settings.CREDENTIAL_SECRET.startswith("autoops-dev") or len(settings.CREDENTIAL_SECRET) < 32:
        problems.append("CREDENTIAL_SECRET 仍是默认值或长度不足 32 字节（凭据加密不安全）")
    for p in problems:
        logger.warning("[安全告警] %s —— 请在 backend/.env 或环境变量中覆盖", p)


@app.on_event("startup")
def on_startup():
    _check_insecure_defaults()
    init_seed()
    _start_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    from app.services import scheduler
    scheduler.shutdown()


def _start_scheduler():
    """启动调度器，并注册所有启用的巡检计划。"""
    from app.services import scheduler
    from app.models import InspectionPlan
    from app.api.plans import run_plan_job

    db = SessionLocal()
    try:
        plans = db.query(InspectionPlan).filter(InspectionPlan.enabled == True).all()
        for p in plans:
            if p.cron:
                scheduler.register_plan(p.id, p.cron, run_plan_job)
    finally:
        db.close()
    scheduler.start()


def _mount_frontend(dist: Path):
    """生产模式：若前端已构建（frontend/dist 存在），由后端直接托管静态资源。

    这样本地部署可以只跑一个进程（一个端口）对外服务，不需要额外的 nginx。
    配置了 nginx/容器反向代理时该逻辑会被自动跳过（dist 由 nginx 托管）。
    """
    index_file = dist / "index.html"
    if not index_file.is_file():
        return

    assets_dir = dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # 不允许吞掉 API 路径，否则错误的接口地址会变成 200 + HTML
        if full_path.startswith(("api/", "docs", "openapi.json", "redoc")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        target = (dist / full_path).resolve()
        # 防目录穿越，且只允许 dist 目录内的文件
        if full_path and target.is_file() and str(target).startswith(str(dist.resolve())):
            return FileResponse(target)
        # 带扩展名的静态文件缺失时返回 404，不要回退成 HTML（否则前端会拿到一段 HTML 当图片/字体）
        if "." in full_path.rsplit("/", 1)[-1]:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return FileResponse(index_file)

    logger.info("已启用前端静态托管: %s", dist)


_mount_frontend(Path(__file__).resolve().parent.parent.parent / "frontend" / "dist")
