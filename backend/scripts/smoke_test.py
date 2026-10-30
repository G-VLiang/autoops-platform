"""端到端冒烟测试：租户隔离、统计看板、产物归档、调度选主与幂等去重。

用法（在 backend 目录，使用项目 venv）：
    ./venv/Scripts/python.exe scripts/smoke_test.py      # Windows
    ./venv/bin/python scripts/smoke_test.py              # Linux/macOS

脚本使用临时数据库与临时产物目录，不污染正式数据；全部断言通过后退出码为 0。
"""
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="autoops_smoke_"))
os.environ["DATABASE_URL"] = f"sqlite:///{TMP / 'smoke.db'}"
os.environ["ARTIFACT_DIR"] = str(TMP / "artifacts")
os.environ["ARTIFACT_BACKEND"] = "local"
os.environ["SCHEDULER_ENABLED"] = "true"
os.environ["SCHEDULER_HEARTBEAT"] = "1"
os.environ["SCHEDULER_LEASE_TTL"] = "3"
os.environ["EXECUTOR_BACKEND"] = "mock"
os.environ["SECRET_KEY"] = "smoke-test-secret-key"
os.environ["INSTANCE_ID"] = "smoke-instance-1"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import User, Tenant, DEFAULT_TENANT_ID  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, extra=""):
    if cond:
        PASSED.append(name)
        print(f"  [OK] {name}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name} {extra}")


def main():
    with TestClient(app) as c:
        print("\n== 1. 健康检查与登录 ==")
        h = c.get("/health").json()
        check("health 返回 ok", h.get("status") == "ok", h)
        check("调度角色为 leader", h.get("scheduler_role") == "leader", h)

        r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        check("admin 登录成功", r.status_code == 200, r.text)
        tok = r.json()["access_token"]
        check("admin 是平台超管", r.json().get("is_super") is True, r.text)
        H = {"Authorization": f"Bearer {tok}"}

        me = c.get("/api/v1/auth/me", headers=H).json()
        check("me 返回默认租户", me.get("tenant_id") == DEFAULT_TENANT_ID, me)

        prov = c.get("/api/v1/auth/providers").json()
        check("providers 含 local", prov.get("local") is True, prov)

        print("\n== 2. 看板统计 ==")
        dash = c.get("/api/v1/stats/dashboard?days=7", headers=H)
        check("dashboard 200", dash.status_code == 200, dash.text[:300])
        d = dash.json()
        check("overview 含主机与任务", "hosts" in d["overview"] and "tasks" in d["overview"], d.keys())
        check("trend 点数=7", len(d["trend"]["points"]) == 7, len(d["trend"]["points"]))
        check("hotspots 结构完整", {"failed_hosts", "failing_templates", "categories"} <= set(d["hotspots"]))

        print("\n== 3. 资产管理 ==")
        groups = c.get("/api/v1/hosts/groups", headers=H).json()
        check("默认租户有演示主机组", len(groups) >= 1, groups)
        gid = groups[0]["id"]
        host = c.post("/api/v1/hosts", headers=H, json={
            "hostname": "smoke-host", "ip": "10.0.0.9", "group_id": gid})
        check("新建主机成功", host.status_code == 200, host.text)
        hid = host.json()["id"]

        print("\n== 4. 任务执行 + 产物归档 ==")
        task = c.post("/api/v1/tasks", headers=H, json={
            "name": "冒烟任务", "task_type": "adhoc", "content": "uptime",
            "target_type": "host", "target_id": hid})
        check("任务执行成功", task.status_code == 200, task.text)
        tid = task.json()["id"]
        check("任务写入 artifact_uri", bool(task.json().get("artifact_uri")), task.json())
        art = c.get(f"/api/v1/tasks/{tid}/artifact", headers=H)
        check("任务产物可下载", art.status_code == 200 and len(art.content) > 50, art.status_code)

        print("\n== 5. 巡检计划 + 报告 ==")
        tpl = c.get("/api/v1/inspections/templates", headers=H).json()[0]
        plan = c.post("/api/v1/plans", headers=H, json={
            "name": "冒烟巡检", "template_id": tpl["id"], "target_type": "host",
            "target_id": hid, "cron": "0 4 * * *", "enabled": True})
        check("创建巡检计划", plan.status_code == 200, plan.text)
        pid = plan.json()["id"]
        run = c.post(f"/api/v1/plans/{pid}/run", headers=H)
        check("立即执行计划", run.status_code == 200, run.text)
        rid = run.json().get("report_id")
        rep = c.get(f"/api/v1/plans/reports/{rid}/artifact", headers=H)
        check("报告产物可下载", rep.status_code == 200, rep.status_code)

        print("\n== 6. 多租户隔离 ==")
        t2 = c.post("/api/v1/tenants", headers=H, json={"code": "acme", "name": "ACME 公司"})
        check("创建租户 acme", t2.status_code == 200, t2.text)
        t2_id = t2.json()["id"]

        db = SessionLocal()
        try:
            db.add(User(username="acme-boss", hashed_password=hash_password("acme123"),
                        role="admin", tenant_id=t2_id, is_super=False))
            db.commit()
        finally:
            db.close()

        r2 = c.post("/api/v1/auth/login", json={"username": "acme-boss", "password": "acme123"})
        check("租户用户登录成功", r2.status_code == 200, r2.text)
        H2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
        check("租户用户非超管", r2.json().get("is_super") is False, r2.json())

        hosts2 = c.get("/api/v1/hosts", headers=H2).json()
        check("租户 B 看不到租户 A 的主机", len(hosts2) == 0, hosts2)
        cross = c.get(f"/api/v1/hosts/{hid}", headers=H2)
        check("跨租户访问主机返回 404", cross.status_code in (404, 405), cross.status_code)
        cross_task = c.get(f"/api/v1/tasks/{tid}", headers=H2)
        check("跨租户访问任务返回 404", cross_task.status_code == 404, cross_task.status_code)
        stats2 = c.get("/api/v1/stats/overview", headers=H2).json()
        check("租户 B 统计为 0 主机", stats2["hosts"]["total"] == 0, stats2["hosts"])
        forbid = c.get("/api/v1/tenants", headers=H2)
        check("普通租户用户无权列租户", forbid.status_code == 403, forbid.status_code)

        # 超管用 X-Tenant-Id 收窄视角
        scoped_hosts = c.get("/api/v1/hosts", headers={**H, "X-Tenant-Id": "acme"}).json()
        check("超管按租户收窄后为空", len(scoped_hosts) == 0, scoped_hosts)

        print("\n== 7. 调度幂等与选主 ==")
        from app.services import scheduler as sch

        key = f"{pid}@202601010000"
        first = sch.claim_run_key(pid, key)
        second = sch.claim_run_key(pid, key)
        check("同一时间槽首次可执行", first is True)
        check("同一时间槽重复被拦截", second is False)

        other = sch.LeaderElection()
        other.id = "smoke-instance-2"
        check("租约有效时其他实例抢不到", other.try_acquire() is False)
        # 手动把租约置为过期，模拟 leader 宕机
        from app.models import SchedulerLock
        from datetime import datetime, timedelta
        db = SessionLocal()
        try:
            db.query(SchedulerLock).filter(SchedulerLock.name == "scheduler").update(
                {"expires_at": datetime.utcnow() - timedelta(seconds=1)})
            db.commit()
        finally:
            db.close()
        check("租约过期后其他实例可接管", other.try_acquire() is True)

        print("\n== 8. 系统状态 ==")
        st = c.get("/api/v1/system/status", headers=H).json()
        check("status 报告产物后端", st["artifact"]["backend"] == "local", st.get("artifact"))
        check("status 报告调度角色", st["scheduler"]["role"] == "leader", st["scheduler"])

    print(f"\n{'='*52}")
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        print("失败项：", ", ".join(FAILED))
        return 1
    print("全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
